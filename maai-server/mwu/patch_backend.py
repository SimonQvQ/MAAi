#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 MAAi 设备类型注入 MWU 后端。

用法: python3 patch_backend.py <MWU源码根> <本mwu目录>
"""
import shutil
import sys
from pathlib import Path


def apply(ds: str) -> str:
    # 1. import bridge/controller
    a = "from maa.controller import ("
    b = (
        "from maa_worker import maa_bridge\n"
        "from maa_worker.maa_controller import MAAiAgentController\n"
        "from maa.controller import ("
    )
    assert ds.count(a) == 1, "import anchor not unique/found"
    ds = ds.replace(a, b, 1)

    # 2. is_controller_supported
    a = 'def is_controller_supported(controller) -> tuple[bool, str]:\n    match controller.type:\n        case "Adb":'
    b = (
        'def is_controller_supported(controller) -> tuple[bool, str]:\n'
        '    match controller.type:\n'
        '        case "MAAi":\n'
        '            return True, ""\n'
        '        case "Adb":'
    )
    assert ds.count(a) == 1, "is_controller_supported anchor"
    ds = ds.replace(a, b, 1)

    # 3. canonicalize_custom_address
    a = '    text = str(address).strip()\n    if device_type in ("Adb", "PlayCover"):'
    b = (
        '    if device_type == "MAAi":\n'
        '        return text if text else "0.0.0.0:17171"\n'
        '    if device_type in ("Adb", "PlayCover"):'
    )
    assert ds.count(a) == 1, "canonicalize anchor"
    ds = ds.replace(a, b, 1)

    # 4. custom_record_to_device
    a = '    if device_type == "PlayCover":\n        return {"type": "PlayCover", "address": address}'
    b = (
        '    if device_type == "MAAi":\n'
        '        return {"type": "MAAi", "address": address}\n'
        '    if device_type == "PlayCover":\n'
        '        return {"type": "PlayCover", "address": address}'
    )
    assert ds.count(a) == 1, "custom_record_to_device anchor"
    ds = ds.replace(a, b, 1)

    # 5. _load_custom_devices 白名单
    a = '                    "PlayCover",\n                ):'
    b = '                    "PlayCover",\n                    "MAAi",\n                ):'
    assert ds.count(a) == 1, "custom devices whitelist anchor"
    ds = ds.replace(a, b, 1)

    # 6. build_device_capabilities search_mode / default_address
    a = (
        '                    "search_mode": "input"\n'
        '                    if controller.type == "PlayCover"\n'
        '                    else "select",\n'
        '                    "default_address": "127.0.0.1:1717"\n'
        '                    if controller.type == "PlayCover"\n'
        '                    else "",'
    )
    b = (
        '                    "search_mode": "input"\n'
        '                    if controller.type in ("PlayCover", "MAAi")\n'
        '                    else "select",\n'
        '                    "default_address": (\n'
        '                        "127.0.0.1:1717"\n'
        '                        if controller.type == "PlayCover"\n'
        '                        else "0.0.0.0:17171"\n'
        '                    )\n'
        '                    if controller.type in ("PlayCover", "MAAi")\n'
        '                    else "",'
    )
    assert ds.count(a) == 1, "capabilities anchor"
    ds = ds.replace(a, b, 1)

    # 7. _find_devices_for_controller
    a = '            case "PlayCover":\n                return devices'
    b = (
        '            case "MAAi":\n'
        '                return devices\n'
        '            case "PlayCover":\n'
        '                return devices'
    )
    assert ds.count(a) == 1, "find_devices anchor"
    ds = ds.replace(a, b, 1)

    # 8. build_device_model_from_config
    a = '        elif device_type == "PlayCover":\n            return DeviceModel('
    b = (
        '        if device_type == "MAAi":\n'
        '            return DeviceModel(\n'
        '                type="MAAi",\n'
        '                controller_name=controller_name,\n'
        '                name=device_address,\n'
        '                address=device_address,\n'
        '            )\n'
        '        if device_type == "PlayCover":\n'
        '            return DeviceModel('
    )
    assert ds.count(a) == 1, "build_device_model anchor"
    ds = ds.replace(a, b, 1)

    # 9. connect 分支
    a = '        match device_type:\n            case "Adb":'
    b = (
        '        match device_type:\n'
        '            case "MAAi":\n'
        '                host, port = maa_bridge.parse_address(device_config.address)\n'
        '                bridge = maa_bridge.MAAiBridge.instance()\n'
        '                bridge.ensure_listening(host, port)\n'
        '                session = bridge.wait_for_agent(timeout=120.0)\n'
        '                if session is not None:\n'
        '                    controller = MAAiAgentController(session)\n'
        '                    status = controller.post_connection().wait().succeeded\n'
        '            case "Adb":'
    )
    assert ds.count(a) == 1, "connect anchor"
    ds = ds.replace(a, b, 1)

    # 10. controller_order
    a = 'controller_order = ["Adb", "Win32", "Gamepad", "PlayCover"]'
    b = 'controller_order = ["MAAi", "Adb", "Win32", "Gamepad", "PlayCover"]'
    assert ds.count(a) == 1, "controller_order anchor"
    ds = ds.replace(a, b, 1)

    return ds


def main():
    mwu = Path(sys.argv[1])
    src = Path(sys.argv[2])
    shutil.copy(src / "maa_bridge.py", mwu / "maa_worker" / "maa_bridge.py")
    shutil.copy(src / "maa_controller.py", mwu / "maa_worker" / "maa_controller.py")

    p = mwu / "maa_worker" / "device_service.py"
    ds = p.read_text(encoding="utf-8")
    ds = apply(ds)
    p.write_text(ds, encoding="utf-8")
    print("[patch_backend] device_service.py patched")

    # Controller.type Literal 加 MAAi
    p2 = mwu / "models" / "interface.py"
    t2 = p2.read_text(encoding="utf-8")
    a2 = '    type: Literal["Adb", "Win32", "MacOS", "PlayCover", "Gamepad"]'
    b2 = '    type: Literal["Adb", "Win32", "MacOS", "PlayCover", "Gamepad", "MAAi"]'
    assert t2.count(a2) == 1, "interface.py Controller.type anchor"
    p2.write_text(t2.replace(a2, b2, 1), encoding="utf-8")
    print("[patch_backend] models/interface.py patched")

    # DeviceType Literal 加 MAAi
    p3 = mwu / "models" / "api.py"
    t3 = p3.read_text(encoding="utf-8")
    a3 = 'DeviceType = Literal["Adb", "Win32", "Gamepad", "PlayCover"]'
    b3 = 'DeviceType = Literal["Adb", "Win32", "Gamepad", "PlayCover", "MAAi"]'
    assert t3.count(a3) == 1, "api.py DeviceType anchor"
    p3.write_text(t3.replace(a3, b3, 1), encoding="utf-8")
    print("[patch_backend] models/api.py patched")


if __name__ == "__main__":
    main()

