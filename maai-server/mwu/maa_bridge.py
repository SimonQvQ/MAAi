# -*- coding: utf-8 -*-
"""MAAi bridge（MWU 集成版）：iPhone MAAiAgent 拨入通道。

协议: MAAi 便捷线格式 —— 4 字节大端长度 + UTF-8 JSON（max 16MB）。
iPhone 端 MAAiAgent 主动拨入，本模块负责监听/收发帧，并产出 AgentSession，
供 MAAiAgentController(MaaCustomController) 驱动。
"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time
import uuid
from queue import Empty, Queue

BUF_MAX = 16 * 1024 * 1024


def _log(*a):
    print(time.strftime("[%H:%M:%S]"), "[maa_bridge]", *a, flush=True)


def encode_frame(obj: dict) -> bytes:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(body)) + body


def _try_decode(buf: bytearray):
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


class AgentSession:
    """一个已连接的 MAAiAgent（iPhone 侧）。"""

    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.buf = bytearray()
        self.connected = True
        self.last_status: dict = {}
        self._lock = threading.Lock()
        self._pending: dict[str, Queue] = {}

    def send(self, msg: dict):
        with self._lock:
            self.sock.sendall(encode_frame(msg))

    def request(self, cmd: str, params: dict, timeout: float = 5.0):
        req_id = uuid.uuid4().hex
        q: Queue = Queue(maxsize=1)
        self._pending[req_id] = q
        self.send({"v": 1, "type": "request", "req_id": req_id, "cmd": cmd, "params": params})
        try:
            return q.get(timeout=timeout)
        except Empty:
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
            _log(f"[agent {self.addr}] STATUS {payload}")
        elif ev == "SCREENSHOT":
            _log(f"[agent {self.addr}] SCREENSHOT event ({len(str(payload.get('data', ''))) } b64)")
        else:
            _log(f"[agent {self.addr}] event {ev}")

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
        _log(f"监听 {self.host}:{self.port}，等待 MAAiAgent 拨入...")
        while True:
            sock, addr = srv.accept()
            s = AgentSession(sock, addr)
            with self._lock:
                self.sessions.append(s)
            threading.Thread(target=self._reader, args=(s,), daemon=True).start()

    def _reader(self, s: AgentSession):
        _log(f"[agent] {s.addr} 连接")
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
            _log(f"[agent] {s.addr} 断开")

    def first_agent(self):
        with self._lock:
            return self.sessions[0] if self.sessions else None


class MAAiBridge:
    """单例：管理监听端口 + 会话，供 MWU device_service 的 MAAi 类型使用。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.server: AgentServer | None = None
        self.thread: threading.Thread | None = None
        self.host = "0.0.0.0"
        self.port = 17171

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def ensure_listening(self, host: str = "0.0.0.0", port: int = 17171) -> bool:
        if self.server and self.thread and self.thread.is_alive():
            return True
        self.host, self.port = host, port
        self.server = AgentServer(host, port)
        self.thread = threading.Thread(target=self.server.start, daemon=True)
        self.thread.start()
        time.sleep(0.3)
        return self.thread.is_alive()

    def first_agent(self):
        return self.server.first_agent() if self.server else None

    def wait_for_agent(self, timeout: float = 120.0):
        """阻塞等待 iPhone MAAiAgent 拨入，返回 AgentSession 或 None。"""
        deadline = time.time() + timeout
        _log(f"等待 MAAiAgent 拨入 (超时 {int(timeout)}s)...")
        while time.time() < deadline:
            s = self.first_agent()
            if s and s.connected:
                _log(f"agent 已就绪: {s.addr}")
                return s
            time.sleep(0.5)
        return None


def parse_address(address: str):
    """解析 "host:port" / "port" -> (host, port)。默认 0.0.0.0:17171。"""
    text = str(address or "").strip()
    if not text:
        return "0.0.0.0", 17171
    if ":" in text:
        h, _, p = text.rpartition(":")
        try:
            return (h or "0.0.0.0"), int(p)
        except ValueError:
            return "0.0.0.0", 17171
    try:
        return "0.0.0.0", int(text)
    except ValueError:
        return "0.0.0.0", 17171
