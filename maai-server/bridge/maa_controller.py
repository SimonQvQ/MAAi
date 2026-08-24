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

try:
    import cv2  # 可选：有则走 JPEG 快路径，无则回退 raw RGBA
except ImportError:
    cv2 = None

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

    @staticmethod
    def _ok(r) -> bool:
        """兼容两种返回：正常响应 result.ok；超时帧顶层 ok:False。"""
        if not r:
            return False
        res = r.get("result") or {}
        return bool(res.get("ok") or r.get("ok"))

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
        if cv2 is not None:
            r = self.agent.request("SCREENCAP", {"format": "jpeg", "quality": self.jpeg_quality})
            data = r.get("result", {}).get("data")
            if self._ok(r) and data:
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
        if self._ok(r) and w > 0 and h > 0 and len(raw) >= w * h * 4:
            arr = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
            return np.ascontiguousarray(arr[:, :, :3][:, :, ::-1])
        return np.zeros((1, 1, 3), np.uint8)

    # ---- 触摸 ----
    def click(self, x: int, y: int) -> bool:
        return self._ok(self.agent.request("CLICK", {"x": int(x), "y": int(y)}))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        return self._ok(self.agent.request("SWIPE", {
            "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
            "duration": int(duration),
        }))

    def touch_down(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return self._ok(self.agent.request("TOUCH_DOWN", {
            "contact": int(contact), "x": int(x), "y": int(y), "pressure": int(pressure),
        }))

    def touch_move(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return self._ok(self.agent.request("TOUCH_MOVE", {
            "contact": int(contact), "x": int(x), "y": int(y), "pressure": int(pressure),
        }))

    def touch_up(self, contact: int) -> bool:
        return self._ok(self.agent.request("TOUCH_UP", {"contact": int(contact)}))

    # ---- 按键 / 文本 ----
    def click_key(self, keycode: int) -> bool:
        return self._ok(self.agent.request("PRESS_KEY", {"key": int(keycode)}))

    def input_text(self, text: str) -> bool:
        return self._ok(self.agent.request("INPUT_TEXT", {"text": text}))

    def key_down(self, keycode: int) -> bool:
        return False  # iOS 注入暂不支持单独 down

    def key_up(self, keycode: int) -> bool:
        return False


class AgentDisplaySink(TaskerEventSink):
    """把任务进度推到 iPhone 浮层（DISPLAY 命令）+ web 状态。"""

    def __init__(self, agent, state=None):
        self.agent = agent
        self.state = state

    def on_raw_notification(self, tasker, msg: str, details: dict[str, Any]) -> None:
        try:
            name = details.get("name", "")
            if msg == "Node.Action.Starting":
                self.agent.request("DISPLAY", {"text": f"执行: {name}"})
                if self.state:
                    self.state.last_node = name
                    self.state.log("节点: " + str(name))
            elif msg == "Tasker.Task.Succeeded":
                self.agent.request("DISPLAY", {"text": "任务完成 ✅"})
                if self.state:
                    self.state.log("任务完成")
            elif msg == "Tasker.Task.Failed":
                self.agent.request("DISPLAY", {"text": "任务失败 ❌"})
                if self.state:
                    self.state.log("任务失败")
        except Exception:
            pass


def run_agent_task(
    agent,
    resource_path: str,
    entry: str,
    pipeline_override: Optional[dict] = None,
    jpeg_quality: int = 70,
    state=None,
):
    """连接一个 agent，加载资源，跑一条任务，返回任务详情。

    state: 可选的 webui.BridgeState，用于上报进度/启停。
    """
    if state:
        state.task_status = "running"
        state.entry = entry
        state.log("加载资源: " + str(resource_path))

    ctrl = MAAiAgentController(agent, jpeg_quality=jpeg_quality)
    if not ctrl.post_connection().wait().succeeded:
        if state:
            state.task_status = "agent 连接失败"
        return {"ok": False, "error": "agent 连接失败"}

    res = Resource()
    res.post_bundle(str(resource_path)).wait()
    if not res.loaded:
        if state:
            state.task_status = "resource 加载失败"
        return {"ok": False, "error": "resource 加载失败"}

    tasker = Tasker()
    if not tasker.bind(res, ctrl):
        if state:
            state.task_status = "tasker bind 失败"
        return {"ok": False, "error": "tasker bind 失败"}
    if not tasker.inited:
        if state:
            state.task_status = "tasker 初始化失败"
        return {"ok": False, "error": "tasker 初始化失败"}

    if state:
        state.tasker = tasker
        state.running = True  # 前置检查全部通过，正式开跑
    sink = AgentDisplaySink(agent, state=state)
    tasker.add_sink(sink)

    try:
        detail = tasker.post_task(entry, pipeline_override).wait().get()
    finally:
        # 无论正常结束还是异常，都必须清掉 tasker，
        # 否则 state.request_start 的运行中守卫会永久拒绝新任务
        if state:
            state.tasker = None
            state.running = False
            state.task_status = "done"
    return detail
