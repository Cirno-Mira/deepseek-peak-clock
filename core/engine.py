# -*- coding: utf-8 -*-
"""峰谷判定引擎
============

纯时间计算，不碰网络也不碰 Qt：给一个时刻，判断现在算高峰还是空闲，
本段区间从哪到哪，接下来几次交接班分别在什么时候。

两个容易踩的点在这里处理掉了：

* 连续假期（比如国庆 + 周末）会让空闲段横跨很多天，所以要先把相邻区间
  **合并**，否则会把中间的 00:00 误报成状态切换；
* 合并后当前段可能被窗口左边缘截断，所以窗口要按需往前翻倍扩展，
  不然进度条会把起点算错。
"""

from __future__ import annotations
from datetime import date, datetime, time as dtime, timedelta
from core.config import TZ_BEIJING, now_beijing
from core.rules import ACTIVE, peak_windows
from core.rules import RUNTIME


def is_all_day_valley(d: date) -> bool:
    """这一天是否整天都是空闲时段（周末 / 法定节假日 / 全部高峰窗口被关掉）。"""
    if not RUNTIME["weekend_holiday_as_valley"]:
        return False
    if d.weekday() >= 5 and ACTIVE["weekend_valley"]:
        return True
    return d in ACTIVE["holidays"]


def valley_intervals(d: date) -> list[tuple[datetime, datetime]]:
    """某一天（北京时间自然日）内的空闲区间列表，半开区间 [start, end)。"""
    day0 = datetime.combine(d, dtime(0, 0), TZ_BEIJING)
    day1 = day0 + timedelta(days=1)
    if is_all_day_valley(d):
        return [(day0, day1)]

    peaks = []
    if not (ACTIVE["peak_workday_only"] and d.weekday() >= 5):
        for s, e in peak_windows():
            peaks.append((datetime.combine(d, s, TZ_BEIJING),
                          datetime.combine(d, e, TZ_BEIJING)))
    peaks.sort()

    # 高峰窗口在一天里的补集就是空闲区间
    out: list[tuple[datetime, datetime]] = []
    cur = day0
    for s, e in peaks:
        if s > cur:
            out.append((cur, s))
        cur = max(cur, e)
    if cur < day1:
        out.append((cur, day1))
    return out


def _window(now: datetime, back: int = 2, fwd: int = 7) -> list[tuple[datetime, datetime]]:
    today = now.date()
    segs: list[tuple[datetime, datetime]] = []
    for i in range(-back, fwd + 1):
        segs.extend(valley_intervals(today + timedelta(days=i)))
    segs.sort()
    return segs


def merged_window(now: datetime | None = None,
                  back: int = 2, fwd: int = 7) -> list[tuple[datetime, datetime]]:
    """
    合并相邻/重叠的空闲区间。
    例：周四 18:00 之后接着中秋假期和周末时，会从「周四 18:00」一直连到
    「下周一 09:00」成为一整段，而不是每天各自断开——否则交接班预告会把
    中间的 00:00 误报成状态切换。
    """
    now = now or now_beijing()
    merged: list[tuple[datetime, datetime]] = []
    for s, e in _window(now, back, fwd):
        if merged and s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def _locate(segs, now):
    """在合并区间表里定位当前时段，并标记是否贴到窗口左边缘（可能被截断）。"""
    for i, (s, e) in enumerate(segs):
        if s <= now < e:
            return True, s, e, i == 0
    prev_end = max((e for _, e in segs if e <= now), default=None)
    next_start = min((s for s, e in segs if s > now), default=None)
    return False, prev_end, next_start, False


def current_period(now: datetime | None = None):
    """
    返回 (是否空闲, 本段起点, 本段终点)。
    空闲段就是空闲区间本身；高峰段则是「上一个空闲结束 -> 下一个空闲开始」。

    长假（比如国庆 + 周末连着十来天）会让当前空闲段横跨很多天，所以窗口要
    一直往前扩，直到当前的这一整段完整落在窗口内——否则进度条会把起点算错。
    """
    now = now or now_beijing()
    back = 2
    while True:
        segs = merged_window(now, back=back, fwd=7)
        off, s, e, truncated = _locate(segs, now)
        if not truncated and s is not None and e is not None:
            return off, s, e
        if back >= 64:
            return (off,
                    s if s is not None else now,
                    e if e is not None else now + timedelta(hours=1))
        back *= 2


def upcoming_switches(now: datetime | None = None, n: int = 3):
    """
    接下来 n 次交接班：[(切换时刻, 切换后是否空闲), ...]。
    长假连成一大片空闲时，向前 7 天可能都凑不满 n 条，所以按需扩窗。
    """
    now = now or now_beijing()
    state = current_period(now)[0]

    fwd = 7
    while True:
        events: list[tuple[datetime, bool]] = []
        for s, e in merged_window(now, back=2, fwd=fwd):
            events.append((s, True))
            events.append((e, False))
        events.sort()

        out: list[tuple[datetime, bool]] = []
        cur = state
        for t, st in events:
            if t <= now or st == cur:
                continue
            out.append((t, st))
            cur = st
            if len(out) >= n:
                break

        if len(out) >= n or fwd >= 64:
            return out
        fwd *= 2


def day_schedule_text(d: date) -> str:
    """今天的值班安排（紧凑一行）。"""
    if is_all_day_valley(d):
        why = "周末" if d.weekday() >= 5 else "法定节假日"
        return f"全天 梁文谷 · 空闲价（{why}）"
    wins = "、".join(f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                     for s, e in peak_windows())
    return f"高峰 {wins} 梁文峰 · 其余时段 梁文谷"


def fmt_delta(td: timedelta) -> str:
    total = max(0, int(td.total_seconds()))
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}天 {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def human_delta(td: timedelta) -> str:
    total = max(0, int(td.total_seconds()))
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, _s = divmod(rem, 60)
    if d:
        return f"{d} 天 {h} 小时"
    if h and m:
        return f"{h} 小时 {m} 分"
    if h:
        return f"{h} 小时"
    if m:
        return f"{m} 分"
    return "不到 1 分钟"


def fmt_switch_time(t: datetime, ref: datetime) -> str:
    d = (t.date() - ref.date()).days
    prefix = {0: "今天", 1: "明天", 2: "后天"}.get(d)
    if prefix is None:
        prefix = t.strftime("%m-%d")
    return f"{prefix} {t.strftime('%H:%M')}"


WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
