#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""maai-bridge —— 连接 iPhone 端 MAAiAgent 与 MaaFramework(Linux) 的最小桥。

协议: MAAi 便捷线格式 —— 4 字节大端长度 + UTF-8 JSON（与
MaaRuntime/src/core/ipc_message.h 完全一致，max 16MB）。

职责:
  1. 监听 17171，接受 MAAiAgent(明日方舟进程) 拨入；
  2. 对每个 agent：发 SCREENCAP/CLICK/SWIPE/... 请求，收 STATUS/SCREENSHOT 事件；
  3. 通过 ctypes 把 agent 包装成 MaaFramework v5 自定义控制器（见 MaaFrameworkFFI，
     需要按实际 SDK 头文件校准符号——v5 与 v4 差异集中在函数签名/结构体字段）。

用法:
  python3 agent_bridge.py --host 0.0.0.0 --port 17171 [--lib ./maafw/libMaaFramework.so]

注意:
  - 没有探测到 MaaFramework 库时，bridge 仍可单独运行（便于先测 agent 通道）。
  - opencv/PIL 任选其一用于 JPEG->RGBA，都没有则 SCREENCAP raw 数据直接透传。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field

BUF_MAX = 16 * 1024 * 1024


# ---------------------------------------------------------------- wire format
def encode_frame(obj: dict) -> bytes:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(body)) + body


def _try_decode(buf: bytearray):
    """返回 (frames, rest)；帧不完整则返回空列表。"""
    frames = []
    while len(buf) >= 4:
        n = struct.unpack(">I", bytes(buf[:4]))[0]
        if n == 0 or n > BUF_MAX:
            return frames, bytearray()
        if len(buf) < 4 + n:
            break
        try:
            frames.append(json.loads(bytes(buf[4:4 + n]).decode("utf-8")))
        except json.JSONDecodeError:
            pass
        del buf[:4 + n]
    return frames, buf


# ---------------------------------------------------------------- agent side
class AgentSession:
    """一个已连接的 MAAiAgent（iPhone 侧）。"""

    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.buf = bytearray()
        self.connected = True
        self.last_status: dict = {}
        self._lock = threading.Lock()
        self._pending: dict[str, queue.Queue] = {}

    def send(self, msg: dict):
        with self._lock:
            self.sock.sendall(encode_frame(msg))

    def request(self, cmd: str, params: dict, timeout: float = 5.0):
        req_id = uuid.uuid4().hex
        q: queue.Queue = queue.Queue(maxsize=1)
        self._pending[req_id] = q
        self.send({"v": 1, "type": "request", "req_id": req_id, "cmd": cmd, "params": params})
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "error": f"timeout: {cmd}"}
        finally:
            self._pending.pop(req_id, None)

    def feed(self, data: bytes):
        self.buf += data
        frames, self.buf = _try_decode(self.buf)
        for m in frames:
            if m.get("type") == "response":
                q = self._pending.get(m.get("req_id", ""))
                if q:
                    q.put(m)
            elif m.get("type") == "event":
                self.handle_event(m)

    def handle_event(self, m: dict):
        ev = m.get("event", "")
        payload = m.get("payload", {})
        if ev == "STATUS":
            self.last_status = payload
            log(f"[agent {self.addr}] STATUS {payload}")
        elif ev == "SCREENSHOT":
            log(f"[agent {self.addr}] SCREENSHOT event ({len(str(payload.get('data','')) )} b64)")
        else:
            log(f"[agent {self.addr}] event {ev}")

    def close(self):
        self.connected = False
        try:
            self.sock.close()
        except OSError:
            pass


class AgentServer:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.sessions: list[AgentSession] = []
        self._lock = threading.Lock()

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(8)
        log(f"bridge 监听 {self.host}:{self.port}，等待 MAAiAgent 拨入...")
        while True:
            sock, addr = srv.accept()
            s = AgentSession(sock, addr)
            with self._lock:
                self.sessions.append(s)
            threading.Thread(target=self._reader, args=(s,), daemon=True).start()

    def _reader(self, s: AgentSession):
        log(f"[agent] {s.addr} 连接")
        try:
            while True:
                data = s.sock.recv(65536)
                if not data:
                    break
                s.feed(data)
        except OSError:
            pass
        finally:
            with self._lock:
                if s in self.sessions:
                    self.sessions.remove(s)
            s.close()
            log(f"[agent] {s.addr} 断开")

    def first_agent(self):
        with self._lock:
            return self.sessions[0] if self.sessions else None


# ---------------------------------------------------------------- MaaFramework FFI（骨架）
class MaaFrameworkFFI:
    """把 AgentSession 包装成 MaaFramework v5 自定义控制器。

    TODO(校准项): 以实际安装的 MaaFramework SDK 头文件为准——
      1. 动态库名/导出符号：MaaCustomControllerCreate / MaaTaskerCreate / ...
      2. MaaCustomControllerCallbacks 回调表字段与顺序（v4/v5 有差异）
      3. MaaImageBuffer 的 SetRawData 接口与尺寸/步长约定
      4. 截图格式：框外建议 agent 返回 raw(RGBA) 再 SetRawData；JPEG 需要 cv2/PIL 解码

    未完成这些校准前，本类只做通道层面的请求封装，不实际注册控制器。
    """

    def __init__(self, lib_path: str | None):
        self.lib_path = lib_path
        self._lib = None
        if lib_path and os.path.exists(lib_path):
            import ctypes
            self._lib = ctypes.CDLL(lib_path)
            log(f"MaaFramework 库已加载: {lib_path}")
        else:
            log("未找到 MaaFramework 库，跳过控制器注册（仅测试 agent 通道）")

    def screencap(self, agent: AgentSession, fmt: str = "jpeg"):
        """向 agent 请求一帧截图，返回 {"ok", "data", "format"}。"""
        return agent.request("SCREENCAP", {"format": fmt, "quality": 70})

    def click(self, agent: AgentSession, x: int, y: int):
        return agent.request("CLICK", {"x": int(x), "y": int(y)})

    def swipe(self, agent, x1, y1, x2, y2, duration=200):
        return agent.request("SWIPE", {"x1": int(x1), "y1": int(y1),
                                       "x2": int(x2), "y2": int(y2),
                                       "duration": int(duration)})

    def display(self, agent: AgentSession, text: str):
        """命令 agent 在游戏浮层上显示当前操作。"""
        return agent.request("DISPLAY", {"text": text})


# ---------------------------------------------------------------- main
def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def main():
    ap = argparse.ArgumentParser(description="maai-bridge")
    ap.add_argument("--host", default=os.environ.get("MAAI_BRIDGE_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MAAI_BRIDGE_PORT", "17171")))
    ap.add_argument("--lib", default=os.environ.get("MAAFW_LIB", "maafw/libMaaFramework.so"))
    ap.add_argument("--demo", action="store_true",
                    help="每 5 秒对第一个 agent 拉一帧截图像素尺寸并滚动一条 DISPLAY")
    args = ap.parse_args()

    server = AgentServer(args.host, args.port)
    ffi = MaaFrameworkFFI(args.lib)

    if args.demo:
        def demo_loop():
            while True:
                time.sleep(5)
                a = server.first_agent()
                if not a:
                    log("[demo] 暂无 agent")
                    continue
                st = a.last_status
                ffi.display(a, "当前操作: 演示中 / 屏幕: " +
                            json.dumps(st.get("screen", {}), ensure_ascii=False))
                r = ffi.screencap(a)
                ok = bool(r.get("ok") and r.get("result", {}).get("data"))
                log(f"[demo] screencap -> {'ok' if ok else 'fail'} ")
        threading.Thread(target=demo_loop, daemon=True).start()

    server.start()


if __name__ == "__main__":
    main()
