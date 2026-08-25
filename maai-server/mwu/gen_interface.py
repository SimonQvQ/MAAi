#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 MAAi interface.json（含完整任务设置 option，定义源自 MAA-Meow）。"""
import json
from pathlib import Path

OPT = {}  # name -> Option dict

def opt(name, type_, label, desc="", **kw):
    o = {"type": type_, "label": label}
    if desc:
        o["description"] = desc
    if type_ == "switch":
        o["cases"] = [{"name": "true", "label": "开启"}, {"name": "false", "label": "关闭"}]
    o.update(kw)
    OPT[name] = o
    return name

# ---------------- 公开招募（MAA-Meow RecruitConfig） ----------------
opt("公招刷新三星", "switch", "刷新三星Tag", "出现非稀有/高资三星Tag时自动刷新", default_case="true")
opt("公招强制刷新", "switch", "强制刷新", "招募券用完后强制刷新", default_case="true")
opt("公招使用加急许可", "switch", "使用加急许可", "招募完成后自动使用加急许可", default_case="false")
opt("公招最大次数", "input", "最大招募次数", "连续招募的最大次数", inputs=[{"name":"times","pipeline_type":"int","default":"4"}], default_case="4")
opt("公招额外Tag策略", "select", "额外Tag策略", "自动公招选择额外Tag的策略",
    cases=[{"name":"0","label":"不选择额外Tag"},{"name":"1","label":"选择额外Tag"},{"name":"2","label":"仅选择稀有Tag"}],
    default_case="0")
opt("公招选三星", "switch", "自动选择三星", "识别到三星词条时自动招募", default_case="true")
opt("公招三星时长", "select", "三星招募时长",
    cases=[{"name":f"{h}","label":f"{h} 小时"} for h in range(1,10)],
    default_case="9")
opt("公招选四星", "switch", "自动选择四星", "识别到四星词条时自动招募", default_case="true")
opt("公招四星时长", "select", "四星招募时长",
    cases=[{"name":f"{h}","label":f"{h} 小时"} for h in range(1,10)],
    default_case="9")
opt("公招选五星", "switch", "自动选择五星", "识别到五星词条时自动招募", default_case="false")
opt("公招保留词条", "switch", "保留词条", "启用保留词条（避免误选，默认保留支援机械）", default_case="false")

# ---------------- 刷理智（FightConfig） ----------------
opt("刷理智使用理智药", "switch", "使用理智药", "理智不足时自动使用理智药", default_case="false")
opt("刷理智药数量", "input", "理智药数量", "本次最多使用的理智药数量",
    inputs=[{"name":"n","pipeline_type":"int","default":"999"}], default_case="999")
opt("刷理智使用源石", "switch", "使用源石", "理智不足时使用源石", default_case="false")
opt("刷理智限制次数", "switch", "限制次数", "限制本次作战次数", default_case="false")
opt("刷理智最大次数", "input", "最大次数", "本次最多作战次数",
    inputs=[{"name":"times","pipeline_type":"int","default":"5"}], default_case="5")

# ---------------- 领取奖励（AwardConfig） ----------------
opt("领取每日周常奖励", "switch", "领取每日/每周任务奖励", "", default_case="true")
opt("领取邮件奖励", "switch", "领取所有邮件奖励", "", default_case="false")
opt("领取免费单抽", "switch", "进行每日免费单抽", "", default_case="false")
opt("领取幸运墙合成玉", "switch", "领取幸运墙合成玉", "", default_case="false")
opt("领取挖矿合成玉", "switch", "领取挖矿合成玉", "", default_case="false")
opt("领取周年月卡", "switch", "领取周年特殊月卡", "", default_case="false")

# ---------------- 基建换班（InfrastConfig） ----------------
opt("基建无人机用途", "select", "无人机用途", "无人机加速的目标",
    cases=[{"name":"Money","label":"龙门币"},{"name":"SyntheticJade","label":"合成玉"},
           {"name":"CombatRecord","label":"作战记录"},{"name":"PureGold","label":"赤金"}],
    default_case="Money")
opt("基建宿舍阈值", "input", "宿舍信赖阈值", "低于该信赖值不换班",
    inputs=[{"name":"pct","pipeline_type":"int","default":"30"}], default_case="30")

# ---------------- 信用商店（MallConfig） ----------------
opt("信用访问好友", "switch", "访问好友", "", default_case="true")
opt("信用战斗", "switch", "信用战斗", "", default_case="false")
opt("信用购物", "switch", "信用购物", "", default_case="true")
opt("信用优先购买", "input", "优先购买", "逗号分隔，如：招聘许可,龙门币",
    inputs=[{"name":"items","pipeline_type":"string","default":"招聘许可,龙门币"}], default_case="招聘许可,龙门币")
opt("信用黑名单", "input", "黑名单", "逗号分隔，如：碳,家具,加急许可",
    inputs=[{"name":"items","pipeline_type":"string","default":"碳,家具,加急许可"}], default_case="碳,家具,加急许可")
opt("信用仅买折扣", "switch", "仅购买折扣商品", "", default_case="false")

TASKS = [
    {"name":"启动游戏","entry":"StartUp","option":[]},
    {"name":"每日任务","entry":"DailyTask","option":[]},
    {"name":"刷理智","entry":"Fight","option":["刷理智使用理智药","刷理智药数量","刷理智使用源石","刷理智限制次数","刷理智最大次数"]},
    {"name":"领取奖励","entry":"Award","option":["领取每日周常奖励","领取邮件奖励","领取免费单抽","领取幸运墙合成玉","领取挖矿合成玉","领取周年月卡"]},
    {"name":"公开招募","entry":"Recruit","option":["公招刷新三星","公招强制刷新","公招使用加急许可","公招最大次数","公招额外Tag策略","公招选三星","公招三星时长","公招选四星","公招四星时长","公招选五星","公招保留词条"]},
    {"name":"基建换班","entry":"Infrast","option":["基建无人机用途","基建宿舍阈值"]},
    {"name":"访问好友","entry":"Visit","option":[]},
    {"name":"信用商店","entry":"Mall","option":["信用访问好友","信用战斗","信用购物","信用优先购买","信用黑名单","信用仅买折扣"]},
    {"name":"集成战略","entry":"Roguelike","option":[]},
]

iface = {
    "interface_version": 2,
    "name": "MAAi",
    "label": "MAAi 明日方舟助手",
    "version": "0.01b",
    "github": "https://github.com/SimonQvQ/MAAi",
    "description": "iPhone 端明日方舟自动化（Docker 服务端 + MAA 官方资源；任务设置定义源自 MAA-Meow）",
    "controller": [
        {"name":"iPhone","type":"MAAi","label":"iPhone (MAAiAgent)",
         "description":"连接 iOS 明日方舟进程（MAAiAgent 浮窗设置服务器地址后自动拨入）"}
    ],
    "resource": [
        {"name":"MAA","label":"MAA 官方资源 (v5.12.2 转换)","path":["resource"]}
    ],
    "task": TASKS,
    "option": OPT,
    "preset": [
        {"name":"oneclick","label":"一键长草","description":"启动游戏 → 每日任务 → 基建换班 → 公开招募 → 刷理智",
         "task":[{"name":"启动游戏"},{"name":"每日任务"},{"name":"基建换班"},{"name":"公开招募"},{"name":"刷理智"}]}
    ],
}

out = str(Path(__file__).resolve().parent / "interface.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(iface, f, ensure_ascii=False, indent=2)
print("written", out, "options:", len(OPT), "tasks:", len(TASKS))
