#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 MAAi 设备类型注入 MWU 后端（自适应 MWU 版本）。

上游 MWU（ravizhan/MWU）分为两类：
  A) 已自带 MAAi 后端（device_service.py 含 case "MAAi"，并有 maa_bridge.py /
     maa_controller.py）-> 本脚本只确保这两个文件拷贝到位，跳过旧版补丁。
  B) 旧版（无 MAAi）-> 执行 10 处 device_service 锚点 patch + models Literal +
     app_state pending 字段；main.py 若是旧架构（/api/start 直接收 task_execution）
     再补 pending 自动执行逻辑；若是新架构（execution.submit_manual + ManualStartPayload
     携带 device/resource，任务启动时自动连接设备）则跳过。

用法: python3 patch_backend.py <MWU源码根> <本mwu目录>
"""
import shutil
import sys
from pathlib import Path


def apply(ds: str) -> str:
    # 1. import bridge/controller
    a = "from maa.controller import ("
    b = ("from maa_worker import maa_bridge\n"
         "from maa_worker.maa_controller import MAAiAgentController\n"
         "from maa.controller import (")
    assert ds.count(a) == 1, "import anchor not unique/found"
    ds = ds.replace(a, b, 1)

    # 2. is_controller_supported
    a = 'def is_controller_supported(controller) -> tuple[bool, str]:\n    match controller.type:\n        case "Adb":'
    b = ('def is_controller_supported(controller) -> tuple[bool, str]:\n'
         '    match controller.type:\n'
         '        case "MAAi":\n'
         '            return True, ""\n'
         '        case "Adb":')
    assert ds.count(a) == 1, "is_controller_supported anchor"
    ds = ds.replace(a, b, 1)

    # 3. canonicalize_custom_address
    a = '    text = str(address).strip()\n    if device_type in ("Adb", "PlayCover"):'
    b = ('    if device_type == "MAAi":\n'
         '        return text if text else "0.0.0.0:17171"\n'
         '    if device_type in ("Adb", "PlayCover"):')
    assert ds.count(a) == 1, "canonicalize anchor"
    ds = ds.replace(a, b, 1)

    # 4. custom_record_to_device
    a = '    if device_type == "PlayCover":\n        return {"type": "PlayCover", "address": address}'
    b = ('    if device_type == "MAAi":\n'
         '        return {"type": "MAAi", "address": address}\n'
         '    if device_type == "PlayCover":\n'
         '        return {"type": "PlayCover", "address": address}')
    assert ds.count(a) == 1, "custom_record_to_device anchor"
    ds = ds.replace(a, b, 1)

    # 5. _load_custom_devices 白名单
    a = '                    "PlayCover",\n                ):'
    b = '                    "PlayCover",\n                    "MAAi",\n                ):'
    assert ds.count(a) == 1, "custom devices whitelist anchor"
    ds = ds.replace(a, b, 1)

    # 6. build_device_capabilities search_mode / default_address
    a = ('                    "search_mode": "input"\n'
         '                    if controller.type == "PlayCover"\n'
         '                    else "select",\n'
         '                    "default_address": "127.0.0.1:1717"\n'
         '                    if controller.type == "PlayCover"\n'
         '                    else "",')
    b = ('                    "search_mode": "input"\n'
         '                    if controller.type in ("PlayCover", "MAAi")\n'
         '                    else "select",\n'
         '                    "default_address": (\n'
         '                        "127.0.0.1:1717"\n'
         '                        if controller.type == "PlayCover"\n'
         '                        else "0.0.0.0:17171"\n'
         '                    )\n'
         '                    if controller.type in ("PlayCover", "MAAi")\n'
         '                    else "",')
    assert ds.count(a) == 1, "capabilities anchor"
    ds = ds.replace(a, b, 1)

    # 7. _find_devices_for_controller
    a = '            case "PlayCover":\n                return devices'
    b = ('            case "MAAi":\n'
         '                return devices\n'
         '            case "PlayCover":\n'
         '                return devices')
    assert ds.count(a) == 1, "find_devices anchor"
    ds = ds.replace(a, b, 1)

    # 8. build_device_model_from_config
    a = '        elif device_type == "PlayCover":\n            return DeviceModel('
    b = ('        if device_type == "MAAi":\n'
         '            return DeviceModel(\n'
         '                type="MAAi",\n'
         '                controller_name=controller_name,\n'
         '                name=device_address,\n'
         '                address=device_address,\n'
         '            )\n'
         '        if device_type == "PlayCover":\n'
         '            return DeviceModel(')
    assert ds.count(a) == 1, "build_device_model anchor"
    ds = ds.replace(a, b, 1)

    # 9. connect 分支
    a = '        match device_type:\n            case "Adb":'
    b = ('        match device_type:\n'
         '            case "MAAi":\n'
         '                host, port = maa_bridge.parse_address(device_config.address)\n'
         '                bridge = maa_bridge.MAAiBridge.instance()\n'
         '                bridge.ensure_listening(host, port)\n'
         '                session = bridge.wait_for_agent(timeout=120.0)\n'
         '                if session is not None:\n'
         '                    controller = MAAiAgentController(session)\n'
         '                    status = controller.post_connection().wait().succeeded\n'
         '            case "Adb":')
    assert ds.count(a) == 1, "connect anchor"
    ds = ds.replace(a, b, 1)

    # 10. controller_order
    a = 'controller_order = ["Adb", "Win32", "Gamepad", "PlayCover"]'
    b = 'controller_order = ["MAAi", "Adb", "Win32", "Gamepad", "PlayCover"]'
    assert ds.count(a) == 1, "controller_order anchor"
    ds = ds.replace(a, b, 1)

    return ds


def _patch_task_service(mwu: Path):
    """把 MAAi 自研任务（公招）分发到 maa_recruit 执行器。"""
    p = mwu / "maa_worker" / "task_service.py"
    t = p.read_text(encoding="utf-8")
    if "maa_recruit" in t:
        print("[patch_backend] task_service.py already patched; skip")
        return
    a = (
        '            for task in task_list:\n                if state.stop_flag:'
    )
    b = (
        '            for task in task_list:\n                if task == "Recruit":\n                    from maa_worker import maa_recruit\n                    self.worker.events.send_log("正在运行任务: " + task)\n                    ok = maa_recruit.run_recruit_task(self.worker, options.get(task, {}))\n                    if ok:\n                        continue\n                    state.last_status = "failed"\n                    state.last_error = state.last_error or "公招任务失败"\n                    self.worker.events.emit_task_failed(task_list, state.last_error)\n                    return\n\n                if state.stop_flag:'
    )
    assert t.count(a) == 1, "task_service run_process anchor"
    p.write_text(t.replace(a, b, 1), encoding="utf-8")
    print("[patch_backend] task_service.py recruit dispatch added")


def _patch_legacy_models(mwu: Path):
    p2 = mwu / "models" / "interface.py"
    t2 = p2.read_text(encoding="utf-8")
    a2 = '    type: Literal["Adb", "Win32", "MacOS", "PlayCover", "Gamepad"]'
    b2 = '    type: Literal["Adb", "Win32", "MacOS", "PlayCover", "Gamepad", "MAAi"]'
    if t2.count(a2) == 1:
        p2.write_text(t2.replace(a2, b2, 1), encoding="utf-8")
        print("[patch_backend] models/interface.py patched")

    p3 = mwu / "models" / "api.py"
    t3 = p3.read_text(encoding="utf-8")
    a3 = 'DeviceType = Literal["Adb", "Win32", "Gamepad", "PlayCover"]'
    b3 = 'DeviceType = Literal["Adb", "Win32", "Gamepad", "PlayCover", "MAAi"]'
    if t3.count(a3) == 1:
        p3.write_text(t3.replace(a3, b3, 1), encoding="utf-8")
        print("[patch_backend] models/api.py patched")


def main():
    mwu = Path(sys.argv[1])
    src = Path(sys.argv[2])
    shutil.copy(src / "maa_bridge.py", mwu / "maa_worker" / "maa_bridge.py")
    shutil.copy(src / "maa_controller.py", mwu / "maa_worker" / "maa_controller.py")
    shutil.copy(src / "recruit_runner.py", mwu / "maa_worker" / "maa_recruit.py")

    _patch_task_service(mwu)

    p = mwu / "maa_worker" / "device_service.py"
    ds = p.read_text(encoding="utf-8")
    if '"MAAi"' in ds:
        print("[patch_backend] upstream already has MAAi backend; skip legacy device/models patch")
        pa = mwu / "app_state.py"
        ta = pa.read_text(encoding="utf-8")
        if "pending_task_execution" not in ta:
            aa = '        self.update_status: dict | None = None\n        self.update_info: dict | None = None'
            if ta.count(aa) == 1:
                pa.write_text(ta.replace(aa, aa + "\n        self.pending_task_execution: dict | None = None", 1), encoding="utf-8")
                print("[patch_backend] app_state.py pending field added")
    else:
        ds = apply(ds)
        p.write_text(ds, encoding="utf-8")
        print("[patch_backend] device_service.py patched")
        _patch_legacy_models(mwu)

        pa = mwu / "app_state.py"
        ta = pa.read_text(encoding="utf-8")
        aa = '        self.update_status: dict | None = None\n        self.update_info: dict | None = None'
        if ta.count(aa) == 1:
            pa.write_text(ta.replace(aa, aa + "\n        self.pending_task_execution: dict | None = None", 1), encoding="utf-8")
            print("[patch_backend] app_state.py pending field added")

        pm = mwu / "main.py"
        tm = pm.read_text(encoding="utf-8")
        if "submit_manual" not in tm and "ManualStartPayload" not in tm:
            # 旧版 main.py：未连接时缓存任务，连接成功后自动执行
            a_start = '@app.post("/api/start")\ndef start(task_execution: TaskExecutionPayload):'
            helper = (
                'def _start_tasks_from_payload(app_state, task_execution) -> dict:\n'
                '    normalized_task_list, normalized_task_options, normalized_pre_tasks = (\n'
                '        normalize_task_execution_payload(\n'
                '            task_execution.task_list,\n'
                '            task_execution.task_options,\n'
                '            interface,\n'
                '            task_execution.preTasks,\n'
                '        )\n'
                '    )\n'
                '    if not normalized_task_list:\n'
                '        return {"status": "failed", "message": "请选择任务"}\n'
                '    if not app_state.worker.tasks.start(\n'
                '        normalized_task_list,\n'
                '        normalized_task_options,\n'
                '        pre_tasks=normalized_pre_tasks,\n'
                '    ):\n'
                '        msg = (\n'
                '            app_state.worker.device_state.last_resource_error\n'
                '            or app_state.worker.device_state.last_device_error\n'
                '            or app_state.worker.agent_state.start_error\n'
                '            or app_state.worker.task_state.last_error\n'
                '            or "任务启动失败"\n'
                '        )\n'
                '        app_state.send_log(msg)\n'
                '        return {"status": "failed", "message": msg}\n'
                '    return {"status": "success"}\n'
                '\n\n\n'
            )
            b_start = helper + a_start
            if tm.count(a_start) == 1:
                tm = tm.replace(a_start, b_start, 1)

            a_nc = '    if not app_state.worker.device_state.connected:\n        msg = "请先连接设备"\n        app_state.send_log(msg)\n        return {"status": "failed", "message": msg}\n'
            b_nc = ('    if not app_state.worker.device_state.connected:\n'
                    '        app_state.pending_task_execution = task_execution.model_dump()\n'
                    '        msg = "设备未连接：任务已缓存，连接后自动执行"\n'
                    '        app_state.send_log(msg)\n'
                    '        return {"status": "success", "message": msg, "pending": True}\n')
            if tm.count(a_nc) == 1:
                tm = tm.replace(a_nc, b_nc, 1)

            a_conn = '    if await asyncio.to_thread(app_state.worker.device.connect, device):\n        return {"status": "success"}\n'
            b_conn = ('    if await asyncio.to_thread(app_state.worker.device.connect, device):\n'
                      '        pending = getattr(app_state, "pending_task_execution", None)\n'
                      '        if pending:\n'
                      '            app_state.pending_task_execution = None\n'
                      '            app_state.send_log("设备已连接，自动开始缓存的任务...")\n'
                      '            try:\n'
                      '                payload = TaskExecutionPayload(**pending)\n'
                      '                return _start_tasks_from_payload(app_state, payload)\n'
                      '            except Exception as e:\n'
                      '                app_state.send_log(f"自动开始任务失败: {e}")\n'
                      '        return {"status": "success"}\n')
            if tm.count(a_conn) == 1:
                tm = tm.replace(a_conn, b_conn, 1)
            pm.write_text(tm, encoding="utf-8")
            print("[patch_backend] main.py pending/auto-start logic added (legacy)")
        else:
            print("[patch_backend] new-arch main.py (execution.submit_manual); auto-connect built-in, skip pending patch")

    print("[patch_backend] done")


if __name__ == "__main__":
    main()