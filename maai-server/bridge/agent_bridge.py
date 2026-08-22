#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""maai-bridge —— 连接 iPhone 端 MAAiAgent 与 MaaFramework(Linux) 的最小桥。

协议: MAAi 便捷线格式 —— 4 字节大端长度 + UTF-8 JSON（与
MaaRuntime/src/core/ipc_message.h 完全一致，max 16MB）。

职责:
  1. 监听 17171，接受 MAAiAgent(明日方舟进程) 拨入；
  2. 对每个 agent：发 SCREENCAP/CLICK/SWIPE/... 请求，收 STATUS/SCREENSHOT 事件；
  3. 通过 maa_controller.MAAiAgentController 把 agent 包装成 MaaFramework v5
     自定义控制器，--run 模式下加载 resource 并驱动 MaaTasker 跑任务。

用法:
  python3 agent_bridge.py --host 0.0.0.0 --port 17171          # 仅监听 agent 通道
  python3 agent_bridge.py --run --entry StartUp --resource ./resource  # 跑任务

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


# ---------------------------------------------------------------- MaaFramework 任务运行

def _run_loop(server: AgentServer, entry: str, resource_path: str, state):
    """等待 agent 拨入，用 maa_controller 跑任务（web 可启停/换入口）。"""
    from maa_controller import run_agent_task

    state.entry = entry
    state.running = True
    log(f"[run] 等待 MAAiAgent 拨入，entry={entry}, resource={resource_path} ...")
    while True:
        if not state.running:
            time.sleep(0.5)
            continue
        agent = server.first_agent()
        if not agent:
            time.sleep(1.0)
            continue
        log(f"[run] 使用 agent {agent.addr} 执行 {state.entry}")
        try:
            detail = run_agent_task(agent, resource_path, state.entry, state=state)
            log(f"[run] 任务结束: {detail}")
        except Exception as exc:
            state.task_status = "error"
            log(f"[run] 任务异常: {exc!r}")
        state.running = False
        time.sleep(0.5)


# ---------------------------------------------------------------- main
def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def main():
    ap = argparse.ArgumentParser(description="maai-bridge")
    ap.add_argument("--host", default=os.environ.get("MAAI_BRIDGE_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MAAI_BRIDGE_PORT", "17171")))
    ap.add_argument("--run", action="store_true", help="等待 agent 拨入后用 MaaFramework 跑任务")
    ap.add_argument("--entry", default=os.environ.get("MAAI_ENTRY", "StartUp"),
                    help="任务入口名（默认 StartUp）")
    ap.add_argument("--resource", default=os.environ.get("MAAI_RESOURCE", "resource"),
                    help="MaaFramework 资源包目录（默认 ./resource）")
    args = ap.parse_args()

    server = AgentServer(args.host, args.port)

    import webui
    state = webui.BridgeState()
    state.server = server
    web_port = int(os.environ.get("MAAI_WEB_PORT", "8080"))
    webui.start_server(state, "0.0.0.0", web_port)
    log(f"webui: http://0.0.0.0:{web_port}")

    if args.run:
        threading.Thread(target=server.start, daemon=True).start()
        _run_loop(server, args.entry, args.resource, state)
    else:
        server.start()


if __name__ == "__main__":
    main()
