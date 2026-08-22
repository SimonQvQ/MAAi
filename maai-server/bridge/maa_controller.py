# -*- coding: utf-8 -*-
"""MAAiAgent -> MaaFramework 自定义控制器。

把 iPhone 端 MAAiAgent（经 MAAi 便捷协议连接的 AgentSession）包装成
MaaFramework v5 的 MaaCustomController，供 MaaTasker 直接驱动跑任务。

依赖官方 Python 绑定: pip install maafw opencv-python-headless numpy
截图: 优先 JPEG + cv2 解码（省流量），无 cv2 时回退 raw RGBA -> BGR。
"""
from __future__ import annotations

import base64
from typing import Any, Optional

import numpy as np

from maa.controller import CustomController
from maa.resource import Resource
from maa.tasker import Tasker, TaskerEventSink


class MAAiAgentController(CustomController):
    """把 AgentSession 暴露成 MaaFramework 自定义控制器。"""

    def __init__(self, agent, jpeg_quality: int = 70):
        self.agent = agent
        self.jpeg_quality = jpeg_quality
        super().__init__()

    # ---- 连接 ----
    def connect(self) -> bool:
        return bool(self.agent.connected)

    def connected(self) -> bool:
        return bool(self.agent.connected)

    def request_uuid(self) -> str:
        return f"MAAiAgent@{self.agent.addr}"

    def get_features(self) -> int:
        # 我们直接实现 click/swipe，不需要框架改用 mouse down/up
        return 0

    def start_app(self, intent: str) -> bool:
        return True  # 明日方舟已在 iPhone 上运行

    def stop_app(self, intent: str) -> bool:
        return True

    # ---- 截图 ----
    def screencap(self) -> np.ndarray:
        # 快路径：JPEG + cv2
        try:
            import cv2
        except Exception:
            cv2 = None
        if cv2 is not None:
            r = self.agent.request("SCREENCAP", {"format": "jpeg", "quality": self.jpeg_quality})
            data = r.get("result", {}).get("data")
            if r.get("ok") and data:
                jpg = base64.b64decode(data)
                img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    return np.ascontiguousarray(img)  # BGR, 与框架约定一致
        # 回退：raw RGBA -> BGR
        r = self.agent.request("SCREENCAP", {"format": "raw"})
        res = r.get("result", {})
        w = int(res.get("width") or 0)
        h = int(res.get("height") or 0)
        raw = base64.b64decode(res.get("data") or "")
        if r.get("ok") and w > 0 and h > 0 and len(raw) >= w * h * 4:
            arr = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
            return np.ascontiguousarray(arr[:, :, :3][:, :, ::-1])
        return np.zeros((1, 1, 3), np.uint8)

    # ---- 触摸 ----
    def click(self, x: int, y: int) -> bool:
        return bool(self.agent.request("CLICK", {"x": int(x), "y": int(y)}).get("ok"))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        return bool(self.agent.request("SWIPE", {
            "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
            "duration": int(duration),
        }).get("ok"))

    def touch_down(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return bool(self.agent.request("TOUCH_DOWN", {
            "contact": int(contact), "x": int(x), "y": int(y), "pressure": int(pressure),
        }).get("ok"))

    def touch_move(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return bool(self.agent.request("TOUCH_MOVE", {
            "contact": int(contact), "x": int(x), "y": int(y), "pressure": int(pressure),
        }).get("ok"))

    def touch_up(self, contact: int) -> bool:
        return bool(self.agent.request("TOUCH_UP", {"contact": int(contact)}).get("ok"))

    # ---- 按键 / 文本 ----
    def click_key(self, keycode: int) -> bool:
        return bool(self.agent.request("PRESS_KEY", {"key": int(keycode)}).get("ok"))

    def input_text(self, text: str) -> bool:
        return bool(self.agent.request("INPUT_TEXT", {"text": text}).get("ok"))

    def key_down(self, keycode: int) -> bool:
        return False  # iOS 注入暂不支持单独 down

    def key_up(self, keycode: int) -> bool:
        return False


class AgentDisplaySink(TaskerEventSink):
    """把任务进度推到 iPhone 浮层（DISPLAY 命令）。"""

    def __init__(self, agent):
        self.agent = agent

    def on_raw_notification(self, tasker, msg: str, details: dict[str, Any]) -> None:
        try:
            if msg == "Node.Action.Starting":
                name = details.get("name", "")
                self.agent.request("DISPLAY", {"text": f"执行: {name}"})
            elif msg == "Tasker.Task.Succeeded":
                self.agent.request("DISPLAY", {"text": "任务完成 ✅"})
            elif msg == "Tasker.Task.Failed":
                self.agent.request("DISPLAY", {"text": "任务失败 ❌"})
        except Exception:
            pass


def run_agent_task(
    agent,
    resource_path: str,
    entry: str,
    pipeline_override: Optional[dict] = None,
    jpeg_quality: int = 70,
):
    """连接一个 agent，加载资源，跑一条任务，返回任务详情。"""
    ctrl = MAAiAgentController(agent, jpeg_quality=jpeg_quality)
    ctrl.post_connection().wait()

    res = Resource()
    res.post_bundle(str(resource_path)).wait()
    if not res.loaded:
        return {"ok": False, "error": "resource 加载失败"}

    tasker = Tasker()
    if not tasker.bind(res, ctrl):
        return {"ok": False, "error": "tasker bind 失败"}
    if not tasker.inited:
        return {"ok": False, "error": "tasker 初始化失败"}

    sink = AgentDisplaySink(agent)
    tasker.add_sink(sink)

    detail = tasker.post_task(entry, pipeline_override).wait().get()
    return detail
