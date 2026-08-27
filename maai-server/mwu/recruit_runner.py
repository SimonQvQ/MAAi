# -*- coding: utf-8 -*-
"""MAAi 公招执行器 —— 纯 maafw 重建 MaaCore 的公招任务逻辑。

用 post_task 驱动 MAA 官方 pipeline 的识别/点击节点（RecruitTags/StartRecruit/
RecruitRefresh/RecruitTimer*/RecruitConfirm/RecruitNow/RecruitFinish 等），
Python 侧完成决策：tag->星级组合、刷新、时长、选择/确认、加急、次数。

依赖：
- 资源 bundle 含 recruitment.json（干员 tag 数据）与修复后的模板节点；
- worker（MaaWorker）已连接 MAAi 设备（device_state.controller 可用）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

CORRECT_NUM_TAGS = 5
SPECIAL_TAGS = ("高级资深干员", "资深干员")
ROBOT_TAGS = ("支援机械", "元素")

# MAA 靠 TemplateConfig 按节点名加载同名模板图的节点（pipeline 里无显式 template）。
# convert_maares.py 会为这些节点补 template=name.png；此处仅作文档/校验。
TEMPLATE_NODES = [
    "Recruit", "RecruitConfirm", "RecruitNowConfirm", "RecruitRefresh",
    "RecruitRefreshConfirm", "RecruitFinish", "RecruitSkip", "RecruitContinue",
    "RecruitTimerDecrement", "RecruitNoPermit", "RecruitNoRefresh", "Return",
]


# ---------- 干员数据 ----------
@dataclass(frozen=True)
class Recruitment:
    name: str
    id: str
    level: int
    tags: frozenset


class RecruitData:
    def __init__(self, json_path: Path):
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        self.all_ops = [
            Recruitment(o["name"], o["id"], int(o.get("rarity", 0)), frozenset(o.get("tags", [])))
            for o in data.get("operators", [])
        ]
        self.all_tags = set(data.get("tags", {}).keys())

    @classmethod
    def load_from_bundle(cls, base_dir) -> "RecruitData":
        for p in (Path(base_dir) / "recruitment.json",
                  Path(base_dir) / "resource" / "recruitment.json",
                  Path(base_dir) / "resources" / "recruitment.json"):
            if p.is_file():
                return cls(p)
        raise FileNotFoundError("找不到 recruitment.json（需 MAA 官方资源转换出的 bundle）")


@dataclass
class RecruitCombs:
    tags: list
    opers: list
    min_level: int = 0
    max_level: int = 0
    avg_level: float = 0.0

    def update(self):
        if not self.opers:
            self.min_level = self.max_level = 0
            self.avg_level = 0.0
            return
        lv = [o.level for o in self.opers]
        self.min_level = min(lv)
        self.max_level = max(lv)
        self.avg_level = sum(lv) / len(lv)


def get_all_combs(tags, all_ops):
    """所有 tag 组合（含干员列表），复刻 MAA recruit_calc::get_all_combs。"""
    rcs = []
    for t in tags:
        ops = [o for o in all_ops if t in o.tags]
        if ops:
            c = RecruitCombs([t], ops)
            c.update()
            rcs.append(c)
    n = len(tags)
    for i in range(n):
        for j in range(i + 1, n):
            ops = [o for o in rcs[i].opers if tags[j] in o.tags]
            if ops:
                c = RecruitCombs(sorted([tags[i], tags[j]]), ops)
                c.update()
                rcs.append(c)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                ops = [o for o in rcs[i].opers if tags[j] in o.tags and tags[k] in o.tags]
                if ops:
                    c = RecruitCombs(sorted([tags[i], tags[j], tags[k]]), ops)
                    c.update()
                    rcs.append(c)
    result = []
    for c in rcs:
        if "高级资深干员" not in c.tags:
            c.opers = [o for o in c.opers if o.level < 6]
            if not c.opers:
                continue
            c.update()
        result.append(c)
    return result


# ---------- 决策 ----------
@dataclass
class RecruitConfig:
    select_level: list = field(default_factory=lambda: [3, 4, 5])
    confirm_level: list = field(default_factory=lambda: [3, 4, 5, 6])
    need_refresh: bool = False
    force_refresh: bool = True
    use_expedited: bool = False
    max_times: int = 4
    extra_tags_mode: int = 0  # 0=NoExtra 1=Extra 2=ExtraOnlyRare
    first_tags: list = field(default_factory=list)
    skip_robot: bool = True
    set_time: bool = True
    desired_time_map: dict = field(
        default_factory=lambda: {3: 9 * 60, 4: 9 * 60, 5: 9 * 60, 6: 9 * 60})


@dataclass
class CalcResult:
    success: bool = False
    force_skip: bool = False
    special_skip: bool = False
    robot_skip: bool = False
    recruitment_time: int = 9 * 60
    select_tags: list = field(default_factory=list)


def _has_preferred(tag_ids, first_tags):
    if not first_tags:
        return False
    for t in tag_ids:
        for p in first_tags:
            if p and p in t:
                return True
    return False


def _sort_combos(combos, has_special):
    def key(c):
        sp = any(t in SPECIAL_TAGS for t in c.tags) if has_special else False
        return (sp, c.min_level, c.max_level, c.avg_level, -len(c.tags))
    combos.sort(key=key, reverse=True)


def get_select_tags(combos, tag_ids, extra_mode, first_tags, has_preferred):
    """复刻 MAA AutoRecruitTask::get_select_tags。"""
    if combos[0].min_level == 3 and first_tags:
        select = []
        for t in tag_ids:
            for p in first_tags:
                if p and p in t:
                    select.append(t)
                    break
            if len(select) == 3:
                return select
        return select
    if extra_mode == 0:
        return list(combos[0].tags)
    select, seen = [], set()
    if extra_mode == 1:
        for c in combos:
            for t in c.tags:
                if t not in seen:
                    seen.add(t)
                    select.append(t)
                    if len(select) == 3:
                        return select
        return select
    # ExtraOnlyRare: 只选高星（>3）tag，尽量多
    min_level = combos[0].min_level
    if min_level == 3:
        return select
    for c in combos:
        if c.min_level < min_level:
            return select
        added = 0
        for t in c.tags:
            if t not in seen:
                seen.add(t)
                select.append(t)
                added += 1
        if len(select) > 3:
            for _ in range(added):
                seen.discard(select.pop())
    return select


def build_config(options: dict) -> RecruitConfig:
    def _b(key, default):
        v = options.get(key)
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() == "true"

    def _i(key, default):
        v = options.get(key)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    select_level = []
    if _b("公招选三星", True):
        select_level.append(3)
    if _b("公招选四星", True):
        select_level.append(4)
    if _b("公招选五星", False):
        select_level.append(5)
    preserve = _b("公招保留词条", False)
    return RecruitConfig(
        select_level=select_level or [3, 4, 5],
        need_refresh=_b("公招刷新三星", True),
        force_refresh=_b("公招强制刷新", True),
        use_expedited=_b("公招使用加急许可", False),
        max_times=max(1, _i("公招最大次数", 4)),
        extra_tags_mode=_i("公招额外Tag策略", 0),
        first_tags=["支援机械"] if preserve else [],
        skip_robot=not preserve,
        set_time=True,
        desired_time_map={
            3: _i("公招三星时长", 9) * 60,
            4: _i("公招四星时长", 9) * 60,
            5: 9 * 60,
            6: 9 * 60,
        },
    )


# ---------- 执行 ----------
class RecruitRunner:
    def __init__(self, worker, recruit: RecruitData, cfg: RecruitConfig):
        self.worker = worker
        self.tasker = worker.tasker
        self.controller = worker.device_state.controller
        self.recruit = recruit
        self.cfg = cfg
        self.sleep = 0.25
        self._force_skipped = set()
        self._last_tags = []

    # ---- maafw 辅助 ----
    def post(self, node, override=None):
        job = self.tasker.post_task(node, override or {})
        job.wait()
        return job

    def _results(self, node, override=None):
        self.post(node, override or {"action": "DoNothing", "next": []})
        nd = self.tasker.get_latest_node(node)
        if not nd or not nd.recognition or not nd.recognition.hit:
            return []
        return list(nd.recognition.all_results or [])

    def _ocr(self, node):
        return [r for r in self._results(node) if getattr(r, "text", None)]

    def _has_node(self, node):
        self.post(node, {"action": "DoNothing", "next": []})
        nd = self.tasker.get_latest_node(node)
        return bool(nd and nd.recognition and nd.recognition.hit)

    def _click(self, x, y):
        if self.controller is not None:
            self.controller.click(int(x), int(y))
        time.sleep(self.sleep)

    def _click_rect(self, box):
        self._click(box.x + box.w // 2, box.y + box.h // 2)

    # ---- 识别 ----
    def _read_tags(self):
        for _ in range(5):
            hits = [r for r in self._ocr("RecruitTags") if r.text in self.recruit.all_tags]
            if len(hits) >= CORRECT_NUM_TAGS:
                self._last_tags = hits[:CORRECT_NUM_TAGS]
                return self._last_tags
            time.sleep(0.5)
        self._last_tags = hits or []
        return self._last_tags

    def _read_timer(self):
        hrs = self._ocr("RecruitTimerH")
        mins = self._ocr("RecruitTimerM")
        cur_h = int(hrs[0].text) if hrs else None
        cur_m = int(mins[0].text) if mins else None
        return cur_h, cur_m

    def _check_home(self):
        return bool(self._ocr("StartRecruit"))

    @staticmethod
    def _slot_index(box):
        cx = box.x + box.w // 2
        cy = box.y + box.h // 2
        return (1 if cx > 640 else 0) + (2 if cy > 444 else 0)

    # ---- 流程 ----
    def run(self):
        if not self._enter_recruit_page():
            self.worker.events.send_log("公招：进入公招页失败")
            return False
        self._hire_all()
        cur = 0
        slot_fail = 0
        try_expedite = self.cfg.use_expedited
        while cur < self.cfg.max_times:
            starts = self._ocr("StartRecruit")
            start = None
            for s in starts:
                if self._slot_index(s.box) not in self._force_skipped:
                    start = s
                    break
            if start is None:
                if not self._check_home():
                    self.worker.events.send_log("公招：不在公招主页，中止")
                    return False
                if not try_expedite:
                    break
                if self._recruit_now():
                    self._hire_all()
                continue
            if slot_fail >= 3:
                self.worker.events.send_log("公招：槽位识别连续失败，中止")
                return False
            if self._recruit_one(start):
                cur += 1
            else:
                slot_fail += 1
        self.worker.events.send_log(f"公招：完成 {cur}/{self.cfg.max_times} 次")
        return True

    def _enter_recruit_page(self):
        self.post("Recruit", {"next": []})
        time.sleep(1.5)
        for _ in range(6):
            if self._check_home() or self._read_tags():
                return True
            time.sleep(1)
        return False

    def _hire_all(self):
        for _ in range(4):
            hits = self._results("RecruitFinish")
            if not hits:
                return
            self.post("RecruitFinish", {"next": []})
            time.sleep(1.2)

    def _recruit_one(self, rect):
        self._click_rect(rect.box)
        time.sleep(0.6)
        calc = self._calc_one()
        if not calc.success:
            self._back_to_home()
            return False
        if calc.force_skip or calc.special_skip or calc.robot_skip:
            self._force_skipped.add(self._slot_index(rect.box))
            self._back_to_home()
            return False
        if self.cfg.set_time:
            self._adjust_timer(calc.recruitment_time)
        for tag in calc.select_tags:
            self._click_tag(tag)
        if not self._confirm():
            self._back_to_home()
            return False
        return True

    def _calc_one(self):
        tags = self._read_tags()
        if not tags:
            return CalcResult()
        tag_ids = [r.text for r in tags]
        has_refresh = self._has_node("RecruitRefresh")
        has_permit = not self._has_node("RecruitNoPermit")
        has_special = any(t in SPECIAL_TAGS for t in tag_ids)
        has_robot = any(t in ROBOT_TAGS for t in tag_ids)
        has_pref = _has_preferred(tag_ids, self.cfg.first_tags)
        combos = get_all_combs(tag_ids, self.recruit.all_ops)
        if not combos:
            return CalcResult()
        _sort_combos(combos, has_special)
        final = combos[0]
        refresh_count = 0
        while (self.cfg.need_refresh and has_refresh and not has_special
               and not (self.cfg.skip_robot and has_robot)
               and final.min_level == 3 and not has_pref):
            if refresh_count >= 3:
                return CalcResult()
            self.post("RecruitRefresh", {"next": []})
            time.sleep(0.8)
            self.post("RecruitRefreshConfirm", {"next": []})
            time.sleep(0.8)
            refresh_count += 1
            tags = self._read_tags()
            if not tags:
                return CalcResult()
            tag_ids = [r.text for r in tags]
            has_special = any(t in SPECIAL_TAGS for t in tag_ids)
            has_robot = any(t in ROBOT_TAGS for t in tag_ids)
            has_pref = _has_preferred(tag_ids, self.cfg.first_tags)
            combos = get_all_combs(tag_ids, self.recruit.all_ops)
            if not combos:
                return CalcResult()
            _sort_combos(combos, has_special)
            final = combos[0]
        if not has_permit:
            return CalcResult(success=True, force_skip=True)
        if not (has_robot or has_special):
            if not (final.min_level == 3 and has_pref) and final.min_level not in self.cfg.confirm_level:
                return CalcResult(success=True, force_skip=True)
        if has_special and final.min_level not in self.cfg.confirm_level:
            return CalcResult(success=True, special_skip=True)
        if has_robot and self.cfg.skip_robot:
            return CalcResult(success=True, robot_skip=True)
        rt = self.cfg.desired_time_map.get(max(final.min_level, 3), 9 * 60)
        if not (final.min_level == 3 and has_pref) and final.min_level not in self.cfg.select_level:
            return CalcResult(success=True, recruitment_time=rt)
        sel = get_select_tags(combos, tag_ids, self.cfg.extra_tags_mode,
                              self.cfg.first_tags, has_pref)
        return CalcResult(success=True, recruitment_time=rt, select_tags=sel)

    def _adjust_timer(self, minutes):
        btns = [r for r in self._results("RecruitTimerDecrement") if getattr(r, "box", None)]
        if len(btns) < 2:
            return
        btns.sort(key=lambda r: r.box.x)
        hour_btn, min_btn = btns[0], btns[1]
        cur_h, cur_m = self._read_timer()
        target_h = minutes // 60
        target_m10 = (minutes % 60) // 10
        if cur_h is not None and target_h < cur_h:
            delta_h = cur_h - target_h
        else:
            temp = target_h + (1 if target_m10 else 0)
            delta_h = (1 + 9 - temp) if 1 < temp else (temp - 1)
        for _ in range(max(0, delta_h)):
            self._click_rect(hour_btn.box)
        if target_m10 > 0:
            if cur_m is not None:
                delta_m = (cur_m // 10 - target_m10) % 6
            else:
                delta_m = (6 - target_m10) % 6
            for _ in range(delta_m):
                self._click_rect(min_btn.box)

    def _click_tag(self, name):
        hits = self._last_tags or self._read_tags()
        for h in hits:
            if h.text == name:
                self._click_rect(h.box)
                return
        time.sleep(0.4)

    def _confirm(self):
        for _ in range(5):
            self.post("RecruitConfirm", {"next": []})
            time.sleep(0.8)
            if self._check_home():
                return True
        return False

    def _recruit_now(self):
        self.post("RecruitNow", {"next": []})
        time.sleep(0.8)
        self.post("RecruitNowConfirm", {"next": []})
        time.sleep(1.2)
        return True

    def _back_to_home(self):
        for _ in range(3):
            if self._check_home():
                return
            self.post("Return", {"next": []})
            time.sleep(0.6)


def run_recruit_task(worker, options: dict) -> bool:
    try:
        cfg = build_config(options or {})
        base = getattr(worker.context, "interface_base_dir", None)
        if base is None:
            raise RuntimeError("worker 无 interface_base_dir")
        rd = RecruitData.load_from_bundle(base)
        return RecruitRunner(worker, rd, cfg).run()
    except Exception as e:
        try:
            worker.events.send_log(f"公招任务异常: {e}")
        except Exception:
            pass
        return False
