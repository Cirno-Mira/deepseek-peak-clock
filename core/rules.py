# -*- coding: utf-8 -*-
"""生效规则与本地缓存
==================

`ACTIVE` 是全局唯一的一份生效规则，界面上的开关也直接改这里；
`RUNTIME` 放那些不该被缓存覆盖的运行期开关。

缓存三级兜底：联网结果 -> 本地磁盘缓存 -> `core.config` 里的内置默认值。
"""

from __future__ import annotations
import json
import os
from datetime import date, datetime, time as dtime
from core.config import (CACHE_NAME, DEFAULT_HOLIDAYS, DEFAULT_MODELS,
                         DEFAULT_PEAK_WINDOWS, DEFAULT_PEAK_WORKDAY_ONLY,
                         DEFAULT_WEEKEND_VALLEY)
from core.paths import app_path


def default_rules() -> dict:
    """内置默认规则（联网与缓存都不可用时的兜底）。"""
    return {
        "peak_windows": list(DEFAULT_PEAK_WINDOWS),
        "peak_workday_only": DEFAULT_PEAK_WORKDAY_ONLY,
        "weekend_valley": DEFAULT_WEEKEND_VALLEY,
        "holidays": {date.fromisoformat(s) for s in DEFAULT_HOLIDAYS},
        "models": [dict(m) for m in DEFAULT_MODELS],
        "origin": "builtin",          # builtin / cache / live
        "source": "内置默认值",
        "fetched_at": None,           # datetime
        "holiday_years": [2026],
        "note": "周一至周五（不含法定节假日）9:00-12:00、14:00-18:00 为高峰",
    }


# 全局生效的规则（界面开关也会改这里）
ACTIVE = default_rules()
RUNTIME = {"weekend_holiday_as_valley": True}


def peak_windows() -> list[tuple[dtime, dtime]]:
    return ACTIVE["peak_windows"]

def apply_payload(payload: dict) -> None:
    """把（联网拿到的或缓存里的）payload 变成生效规则。"""
    ACTIVE["peak_windows"] = [(dtime(int(a.hour), int(a.minute)), dtime(int(b.hour), int(b.minute)))
                              for a, b in ((_as_time(x), _as_time(y))
                                           for x, y in payload["peak_windows"])]
    ACTIVE["peak_workday_only"] = bool(payload.get("peak_workday_only", True))
    ACTIVE["weekend_valley"] = bool(payload.get("weekend_valley", True))
    ACTIVE["holidays"] = {_as_date(s) for s in payload.get("holidays", [])}
    ACTIVE["models"] = payload.get("models") or ACTIVE["models"]
    ACTIVE["origin"] = payload.get("origin", "live")
    ACTIVE["source"] = payload.get("source", "")
    ACTIVE["holiday_years"] = payload.get("holiday_years", [])
    ACTIVE["holiday_error"] = payload.get("holiday_error", "")
    ACTIVE["note"] = payload.get("note", ACTIVE.get("note", ""))
    fa = payload.get("fetched_at")
    ACTIVE["fetched_at"] = datetime.strptime(fa, "%Y-%m-%d %H:%M:%S") if fa else None
    RUNTIME["weekend_holiday_as_valley"] = ACTIVE["weekend_valley"]


def _as_time(x):
    if isinstance(x, dtime):
        return x
    if isinstance(x, (list, tuple)):
        return dtime(int(x[0]), int(x[1]))
    h, m = str(x).split(":")[:2]
    return dtime(int(h), int(m))


def _as_date(x) -> date:
    """联网/缓存里是 ISO 字符串，但内置默认值直接就是 date，两种都要认。"""
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x))


def payload_to_json(payload: dict) -> str:
    def conv(o):
        if isinstance(o, dtime):
            return o.strftime("%H:%M")
        if isinstance(o, date):
            return o.isoformat()
        raise TypeError(str(type(o)))
    return json.dumps(payload, ensure_ascii=False, indent=2, default=conv)


def cache_path() -> str:
    """缓存文件路径：优先放程序目录，不可写则退回用户目录。"""
    candidate = app_path(CACHE_NAME)
    try:
        with open(candidate, "a", encoding="utf-8"):
            pass
        return candidate
    except OSError:
        return os.path.join(os.path.expanduser("~"), CACHE_NAME)


def load_cache() -> dict | None:
    try:
        with open(cache_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not data.get("peak_windows") or not data.get("models"):
            return None
        data["origin"] = "cache"
        return data
    except Exception:
        return None


def save_cache(payload: dict) -> None:
    try:
        with open(cache_path(), "w", encoding="utf-8") as fh:
            fh.write(payload_to_json(payload))
    except OSError:
        pass

def describe_rules() -> None:
    """把当前生效的规则打到终端（自检和 --fetch 用）。"""
    print(f"数据来源   : {ACTIVE['origin']} / {ACTIVE['source']}")
    print(f"更新时间   : {ACTIVE.get('fetched_at') or '从未'}")
    print(f"高峰时段   : {'、'.join(f'{s:%H:%M}-{e:%H:%M}' for s, e in peak_windows())}"
          f"（{'仅周一至周五' if ACTIVE['peak_workday_only'] else '每天'}）")
    print(f"周末/节假日: {'全天按空闲时段' if ACTIVE['weekend_valley'] else '不特殊处理'}")
    years = ACTIVE.get("holiday_years") or []
    print(f"法定节假日 : {len(ACTIVE['holidays'])} 天"
          f"{'（' + '、'.join(str(y) for y in years) + '）' if years else '（内置）'}")
    for m in ACTIVE["models"]:
        print(f"  {m['name']:<16} 空闲 {m['idle']}")
        print(f"  {'':<16} 高峰 {m['peak']}")
