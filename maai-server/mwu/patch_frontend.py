#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 MAAi 设备类型注入 MWU 前端源码。

用法: python3 patch_frontend.py <MWU源码根>
"""
import sys
from pathlib import Path


def rep1(text: str, old: str, new: str, tag: str) -> str:
    n = text.count(old)
    if n == 0:
        print(f"[patch_frontend] WARN: {tag} anchor not found")
        return text
    return text.replace(old, new)


def main():
    f = Path(sys.argv[1]) / "front" / "src"

    # ---------- device.ts ----------
    p = f / "services" / "api" / "modules" / "device.ts"
    t = p.read_text(encoding="utf-8")

    t = rep1(
        t,
        'export type DeviceControllerType = "Adb" | "Win32" | "Gamepad" | "PlayCover"',
        'export type DeviceControllerType = "Adb" | "Win32" | "Gamepad" | "PlayCover" | "MAAi"',
        "device.ts DeviceControllerType",
    )
    t = rep1(
        t,
        "export interface PlayCoverDevice {\n  type: \"PlayCover\"\n  name?: string\n  address: string\n  uuid?: string\n}",
        "export interface PlayCoverDevice {\n  type: \"PlayCover\"\n  name?: string\n  address: string\n  uuid?: string\n}\n\nexport interface MAAiDevice {\n  type: \"MAAi\"\n  name?: string\n  address: string\n}",
        "device.ts MAAiDevice",
    )
    t = rep1(
        t,
        "export type ConnectableDevice = AdbDevice | Win32Device | GamepadDevice | PlayCoverDevice",
        "export type ConnectableDevice = AdbDevice | Win32Device | GamepadDevice | PlayCoverDevice | MAAiDevice",
        "device.ts ConnectableDevice",
    )
    p.write_text(t, encoding="utf-8")

    # ---------- deviceConnection.ts ----------
    p = f / "stores" / "device" / "deviceConnection.ts"
    t = p.read_text(encoding="utf-8")

    # 把“是否地址输入型设备”判定扩展为 PlayCover 或 MAAi
    t = rep1(
        t,
        '=== "PlayCover"',
        '=== "PlayCover" || === "MAAi"',
        "deviceConnection type==PlayCover",
    )
    # buildPlayCoverDevice 返回正确类型
    t = rep1(
        t,
        'return { device: { type: "PlayCover", address } }',
        'const ctype = this.selectedControllerCapability?.type === "MAAi" ? "MAAi" : "PlayCover"\n      return { device: { type: ctype, address } as ConnectableDevice }',
        "deviceConnection buildPlayCoverDevice",
    )
    # 存储设备类型（尾部默认分支）
    t = rep1(
        t,
        '  return {\n    type: "PlayCover",\n    controller_name: controllerName,',
        '  return {\n    type: deviceInfo.type === "MAAi" ? "MAAi" : "PlayCover",\n    controller_name: controllerName,',
        "deviceConnection buildStored",
    )
    p.write_text(t, encoding="utf-8")

    # ---------- HomeView.vue ----------
    p = f / "views" / "HomeView.vue"
    t = p.read_text(encoding="utf-8")
    t = rep1(
        t,
        ":is-play-cover=\"deviceStore.selectedControllerCapability?.type === 'PlayCover'\"",
        ":is-play-cover=\"deviceStore.selectedControllerCapability?.type === 'PlayCover' || deviceStore.selectedControllerCapability?.type === 'MAAi'\"",
        "HomeView is-play-cover",
    )
    p.write_text(t, encoding="utf-8")

    # ---------- SchedulerTaskDialog.vue ----------
    p = f / "components" / "settings" / "dialogs" / "SchedulerTaskDialog.vue"
    t = p.read_text(encoding="utf-8")
    t = rep1(
        t,
        'return type === "Adb" || type === "Win32" || type === "Gamepad" || type === "PlayCover"',
        'return type === "Adb" || type === "Win32" || type === "Gamepad" || type === "PlayCover" || type === "MAAi"',
        "Scheduler isDeviceControllerType",
    )
    t = rep1(
        t,
        'const isPlayCover = computed(() => selectedControllerType.value === "PlayCover")',
        'const isPlayCover = computed(() => selectedControllerType.value === "PlayCover" || selectedControllerType.value === "MAAi")',
        "Scheduler isPlayCover",
    )
    p.write_text(t, encoding="utf-8")

    print("[patch_frontend] done")


if __name__ == "__main__":
    main()

