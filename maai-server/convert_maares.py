#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert_maares —— 把 MAA 官方资源(MAA 语法)转换为标准 MaaFramework bundle。

MAA(及 MAA-Meow) 资源基于 MaaFramework 格式，但使用少量 MAA 扩展动作/识别名
（ClickSelf/ClickRect/Stop/Input/OcrDetect/MatchTemplate 等），且 OCR 模型布局
不同。本脚本做规范化，输出标准 bundle（pipeline/ + image/ + model/ocr/），
可直接被 MaaFramework post_bundle 加载。

用法:
  python3 convert_maares.py <MAA_resource_dir> <out_dir>
"""
from __future__ import annotations

import json
import os
import shutil
import sys

# ---- MAA 扩展 -> 标准 MaaFramework 动作/识别名 ----
ACTION_MAP = {
    "ClickSelf": "Click",
    "ClickRect": "Click",
    "Stop": "DoNothing",
    "Input": "InputText",  # 标准动作是 InputText
}
ALG_MAP = {
    "OcrDetect": "OCR",
    "MatchTemplate": "TemplateMatch",
}
# MAA 特有字段，转换时剔除（避免解析器疑惑）
DROP_FIELDS = {"Doc", "specificRect_Doc", "rectMove_Doc", "specialParams_Doc", "isAscii"}


def convert_task(node: dict) -> dict:
    """转换单个 pipeline 节点为标准语法。"""
    out = {}
    for k, v in node.items():
        if k in DROP_FIELDS:
            continue
        if k == "action" and isinstance(v, str):
            out[k] = ACTION_MAP.get(v, v)
        elif k == "algorithm" and isinstance(v, str):
            out[k] = ALG_MAP.get(v, v)
        elif k == "specialParams" and isinstance(v, list) and v:
            # MAA 滑动参数 [duration, ...] -> 标准 duration
            out["duration"] = int(v[0])
        elif k == "inputText":
            out["text"] = v  # MAA Input -> 标准 Text.text
        else:
            out[k] = v
    return out


def load_task_files(res_dir: str) -> dict:
    """收集 MAA 任务定义（tasks.json 单文件 或 tasks/ 目录多个 json）。"""
    merged = {}
    cand = [
        os.path.join(res_dir, "tasks.json"),
        os.path.join(res_dir, "tasks", "tasks.json"),
    ]
    for p in cand:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged.update(data)
    # tasks/ 目录下所有 json（若存在）
    tasks_dir = os.path.join(res_dir, "tasks")
    if os.path.isdir(tasks_dir):
        for root, _, files in os.walk(tasks_dir):
            for fn in sorted(files):
                if fn.endswith(".json"):
                    p = os.path.join(root, fn)
                    try:
                        with open(p, encoding="utf-8") as f:
                            data = json.load(f)
                        if isinstance(data, dict):
                            merged.update(data)
                    except Exception:
                        pass
    return merged


def clean_refs(nodes: dict) -> dict:
    """
    引用完整性处理：
      - #self (MAA 扩展) -> 节点自身名（循环）；
      - 标准锚点 #next/#back 保留；
      - 指向不存在节点的普通引用剔除（MAA 资源偶有悬空 next）。
    """
    valid = set(nodes.keys())
    LIST_FIELDS = ["next", "sub", "on_error", "exceededNext", "reduceOtherTimes", "clickPositions"]
    for name, node in nodes.items():
        for field in LIST_FIELDS:
            v = node.get(field)
            if not isinstance(v, list):
                continue
            keep = []
            for x in v:
                if isinstance(x, str) and x.startswith("#"):
                    if x == "#self":
                        keep.append(name)
                    # 其它 # 锚点(#next/#back等)：标准 MaaFramework 不支持，丢弃
                elif isinstance(x, str):
                    if x in valid:
                        keep.append(x)
                else:
                    keep.append(x)
            if keep:
                node[field] = keep
            else:
                node.pop(field, None)
    return nodes


def convert(res_dir: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    # 1) pipeline
    tasks = load_task_files(res_dir)
    converted = {name: convert_task(node) for name, node in tasks.items() if isinstance(node, dict)}
    converted = clean_refs(converted)
    pipe_dir = os.path.join(out_dir, "pipeline")
    os.makedirs(pipe_dir, exist_ok=True)
    with open(os.path.join(pipe_dir, "tasks.json"), "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)
    print(f"[convert] pipeline nodes: {len(converted)} -> {pipe_dir}/tasks.json")

    # 2) image（template/ 内容）
    templ = os.path.join(res_dir, "template")
    img_dir = os.path.join(out_dir, "image")
    if os.path.isdir(templ):
        shutil.copytree(templ, img_dir, dirs_exist_ok=True)
        n = sum(len(fs) for _, _, fs in os.walk(img_dir))
        print(f"[convert] image files: {n} -> {img_dir}")

    # 3) model/ocr（标准 OCR 布局）
    model_dir = os.path.join(out_dir, "model", "ocr")
    os.makedirs(model_dir, exist_ok=True)
    mapping = [
        ("PaddleOCR/det/inference.onnx", "det.onnx"),
        ("PaddleOCR/rec/inference.onnx", "rec.onnx"),
        ("PaddleOCR/rec/keys.txt", "keys.txt"),
        ("onnx/deploy_direction_cls.onnx", "cls.onnx"),
    ]
    for rel, target in mapping:
        src = os.path.join(res_dir, *rel.split("/"))
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(model_dir, target))
    print("[convert] model/ocr:", sorted(os.listdir(model_dir)))

    # 4) 数据文件原样复制（stages.json 等，MaaFramework 会忽略）
    for fn in os.listdir(res_dir):
        p = os.path.join(res_dir, fn)
        if os.path.isfile(p) and fn not in ("tasks.json", "config.json", "ocr_config.json", "version.json"):
            shutil.copy(p, os.path.join(out_dir, fn))
    print("[convert] done ->", out_dir)


def main():
    if len(sys.argv) != 3:
        print("usage: convert_maares.py <MAA_resource_dir> <out_dir>", file=sys.stderr)
        sys.exit(2)
    convert(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
