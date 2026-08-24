# -*- coding: utf-8 -*-
"""maai-webui —— MAAi 轻量 Web 界面（替代 VNC）。

在 bridge 进程内起一个 HTTP 服务，展示 agent 连接状态、任务进度、实时截图。
标准库实现，无第三方依赖。

用法: 由 agent_bridge.py --run 模式内部启动，或单独:
  python3 webui.py --port 8080
"""
from __future__ import annotations

import argparse
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MAAi 控制台</title>
<style>
  body { margin:0; font-family: system-ui, -apple-system, sans-serif; background:#0f1115; color:#e6e6e6; }
  .wrap { max-width: 720px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 18px; }
  .card { background:#1a1d24; border:1px solid #2a2e38; border-radius:10px; padding:14px; margin:10px 0; }
  .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .dot { width:10px; height:10px; border-radius:50%; background:#666; display:inline-block; }
  .dot.on { background:#2ecc71; }
  .dot.off { background:#e74c3c; }
  img { width:100%; border-radius:8px; background:#000; min-height:160px; }
  button { background:#2563eb; color:#fff; border:0; padding:8px 14px; border-radius:8px; font-size:14px; cursor:pointer; }
  button:disabled { opacity:.5; }
  input { background:#0f1115; border:1px solid #2a2e38; color:#e6e6e6; padding:8px; border-radius:8px; }
  pre { font-size:12px; color:#9aa0aa; white-space:pre-wrap; }
  .big { font-size:15px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>MAAi 控制台 <span id="ver" style="font-size:12px;color:#888"></span></h1>
  <div class="card">
    <div class="row">
      <span class="dot" id="dot"></span>
      <span class="big" id="conn">未连接</span>
      <span style="color:#888" id="addr"></span>
    </div>
    <div class="row" style="margin-top:8px">
      <span>任务: <b id="entry"></b></span>
      <span>状态: <b id="task"></b></span>
    </div>
    <div class="big" style="margin-top:8px" id="node">等待...</div>
  </div>
  <div class="card">
    <div class="row" style="justify-content:space-between">
      <b>实时画面</b>
      <button id="shot" onclick="snap()">截图</button>
    </div>
    <img id="screen" src="" alt="screenshot">
  </div>
  <div class="card">
    <div class="row">
      <b>开始任务</b>
      <input id="entry_input" placeholder="StartUp" value="StartUp">
      <button onclick="start()">开始</button>
      <button onclick="stop()" style="background:#dc2626">停止</button>
    </div>
    <pre id="log"></pre>
  </div>
</div>
<script>
  var dots = document.getElementById('dot');
  var conn = document.getElementById('conn');
  var addr = document.getElementById('addr');
  var entry = document.getElementById('entry');
  var task = document.getElementById('task');
  var node = document.getElementById('node');
  var log = document.getElementById('log');
  var img = document.getElementById('screen');

  function poll() {
    fetch('/api/status').then(function(r){ return r.json(); }).then(function(s){
      dots.className = 'dot ' + (s.connected ? 'on' : 'off');
      conn.textContent = s.connected ? '已连接' : '未连接';
      addr.textContent = s.addr || '';
      entry.textContent = s.entry || '-';
      task.textContent = s.task_status || '-';
      node.textContent = s.last_node || '等待...';
      var t = s.log || '';
      if (t) { log.textContent = t.slice(-800); log.scrollTop = log.scrollHeight; }
    }).catch(function(){});
  }
  function snap() {
    img.src = '/api/screenshot?t=' + Date.now();
  }
  function start() {
    var e = document.getElementById('entry_input').value || 'StartUp';
    fetch('/api/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({entry:e})});
  }
  function stop() {
    fetch('/api/stop', {method:'POST'});
  }
  snap();
  setInterval(poll, 1000);
  setInterval(snap, 2000);
</script>
</body>
</html>
"""


class BridgeState:
    """bridge 与 web 共享的运行状态。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.server = None  # 由 agent_bridge 注入 AgentServer
        self.running = False
        self.entry = ""
        self.task_status = "idle"
        self.last_node = ""
        self.log_lines = []
        self.tasker = None  # 由 _run_loop 设置

    def log(self, text: str):
        with self.lock:
            self.log_lines.append("[" + time.strftime("%H:%M:%S") + "] " + text)
            if len(self.log_lines) > 200:
                self.log_lines = self.log_lines[-200:]

    def first_agent(self):
        return self.server.first_agent() if self.server else None

    def status(self) -> dict:
        with self.lock:
            a = self.first_agent()
            return {
                "connected": bool(a),
                "addr": str(getattr(a, "addr", "")) if a else "",
                "running": self.running,
                "entry": self.entry,
                "task_status": self.task_status,
                "last_node": self.last_node,
                "log": "\n".join(self.log_lines),
                "time": time.time(),
            }


def make_handler(state: BridgeState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                self._send(200, json.dumps(state.status(), ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            elif path == "/api/screenshot":
                a = state.first_agent()
                if not a:
                    self._send(404, b"no agent", "text/plain")
                    return
                try:
                    r = a.request("SCREENCAP", {"format": "jpeg", "quality": 70})
                    res = r.get("result", {})
                    data = res.get("data")
                    if res.get("ok") and data:
                        jpg = base64.b64decode(data)
                        self._send(200, jpg, "image/jpeg")
                    else:
                        self._send(500, b"capture failed", "text/plain")
                except Exception as exc:
                    self._send(500, str(exc).encode("utf-8"), "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/start":
                try:
                    ln = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(ln) or b"{}")
                    state.entry = body.get("entry") or "StartUp"
                    state.running = True
                    state.task_status = "pending"
                    state.log("开始任务: " + state.entry)
                    self._send(200, b"ok", "text/plain")
                except Exception as exc:
                    self._send(500, str(exc).encode("utf-8"), "text/plain")
            elif path == "/api/stop":
                try:
                    if state.tasker is not None:
                        state.tasker.post_stop()
                        state.task_status = "stopping"
                        state.log("请求停止")
                    self._send(200, b"ok", "text/plain")
                except Exception as exc:
                    self._send(500, str(exc).encode("utf-8"), "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

    return Handler


def start_server(state: BridgeState, host: str = "0.0.0.0", port: int = 8080):
    srv = ThreadingHTTPServer((host, port), make_handler(state))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    srv = start_server(BridgeState(), args.host, args.port)
    print("webui on http://%s:%d" % (args.host, args.port))
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
