# -*- coding: utf-8 -*-
"""MAAiAgent -> MaaFramework 自定义控制器（MWU 集成版）。

把 iPhone 端 MAAiAgent（经 MAAi 便捷协议连接的 AgentSession）包装成
MaaFramework v5 的 MaaCustomController，供 MWU 的 MaaTasker 直接驱动。
"""
from __future__ import annotations

import base64

import numpy as np

try:
    import cv2  # 可选：有则走 JPEG 快路径，无则回退 raw RGBA
except ImportError:
    cv2 = None

from maa.controller import CustomController


class MAAiAgentController(CustomController):
    """把 AgentSession 暴露成 MaaFramework 自定义控制器。"""

    def __init__(self, agent, jpeg_quality: int = 70):
        self.agent = agent
        self.jpeg_quality = jpeg_quality
        super().__init__()

    def connect(self) -> bool:
        return bool(self.agent.connected)

    def connected(self) -> bool:
        return bool(self.agent.connected)

    def request_uuid(self) -> str:
        return f"MAAiAgent@{self.agent.addr}"

    @staticmethod
    def _ok(r) -> bool:
        if not r:
            return False
        res = r.get("result") or {}
        return bool(res.get("ok") or r.get("ok"))

    def get_features(self) -> int:
        return 0

    def start_app(self, intent: str) -> bool:
        return True

    def stop_app(self, intent: str) -> bool:
        return True

    def screencap(self) -> np.ndarray:
        if cv2 is not None:
            r = self.agent.request("SCREENCAP", {"format": "jpeg", "quality": self.jpeg_quality})
            data = r.get("result", {}).get("data")
            if self._ok(r) and data:
                jpg = base64.b64decode(data)
                img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    return np.ascontiguousarray(img)
        r = self.agent.request("SCREENCAP", {"format": "raw"})
        res = r.get("result", {})
        w = int(res.get("width") or 0)
        h = int(res.get("height") or 0)
        raw = base64.b64decode(res.get("data") or "")
        if self._ok(r) and w > 0 and h > 0 and len(raw) >= w * h * 4:
            arr = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
            return np.ascontiguousarray(arr[:, :, :3][:, :, ::-1])
        return np.zeros((1, 1, 3), np.uint8)

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

    def click_key(self, keycode: int) -> bool:
        return self._ok(self.agent.request("PRESS_KEY", {"key": int(keycode)}))

    def input_text(self, text: str) -> bool:
        return self._ok(self.agent.request("INPUT_TEXT", {"text": text}))

    def key_down(self, keycode: int) -> bool:
        return False

    def key_up(self, keycode: int) -> bool:
        return False
