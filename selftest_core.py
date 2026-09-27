# -*- coding: utf-8 -*-
"""
核心层自检
==========

不依赖 PyQt5、不联网、不写真实缓存：把峰谷排程、规则 payload、定价页解析
和路径处理都跑一遍。改完 `core/` 里的东西先跑这个。

    python selftest_core.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time as dtime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import rules as R                                        # noqa: E402
from core.config import (DEFAULT_MODELS, TZ_BEIJING,             # noqa: E402
                         now_beijing)
from core.engine import (WEEKDAYS, current_period, day_schedule_text,   # noqa: E402
                         fmt_delta, fmt_switch_time, human_delta,
                         is_all_day_valley, upcoming_switches,
                         valley_intervals)
from core.feed import parse_pricing_page, _strip_html, _squash     # noqa: E402
from core.paths import app_dir, app_path, icon_path, resource_path  # noqa: E402
from core.rules import (ACTIVE, RUNTIME, apply_payload,            # noqa: E402
                        default_rules, load_cache, payload_to_json,
                        peak_windows, save_cache)

TZ = TZ_BEIJING
FAILS: list[str] = []


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def check(label: str, got, want) -> None:
    ok = got == want
    if not ok:
        FAILS.append(label)
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"   [{got!r}]"))
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")


def at(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def state(y, m, d, hh, mm=0):
    """返回 (峰/谷, 本段起点, 本段终点)，时间用 MM-DD HH:MM。"""
    off, s, e = current_period(at(y, m, d, hh, mm))
    return ("谷" if off else "峰", f"{s:%m-%d %H:%M}", f"{e:%m-%d %H:%M}")


section("1. 工作日窗口边界（2026-09-23 周三）")
check("08:59 空闲", state(2026, 9, 23, 8, 59)[0], "谷")
check("09:00 进入高峰", state(2026, 9, 23, 9, 0)[0], "峰")
check("11:59 仍高峰", state(2026, 9, 23, 11, 59)[0], "峰")
check("12:00 午休转空闲", state(2026, 9, 23, 12, 0)[0], "谷")
check("13:59 仍空闲", state(2026, 9, 23, 13, 59)[0], "谷")
check("14:00 进入下午高峰", state(2026, 9, 23, 14, 0)[0], "峰")
check("17:59 仍高峰", state(2026, 9, 23, 17, 59)[0], "峰")
check("18:00 转空闲", state(2026, 9, 23, 18, 0)[0], "谷")
check("上午高峰段区间", state(2026, 9, 23, 10, 0), ("峰", "09-23 09:00", "09-23 12:00"))
check("午休空闲段区间", state(2026, 9, 23, 12, 30), ("谷", "09-23 12:00", "09-23 14:00"))
check("下午高峰段区间", state(2026, 9, 23, 15, 0), ("峰", "09-23 14:00", "09-23 18:00"))
check("夜间空闲段跨到次日 09:00",
      state(2026, 9, 23, 20, 0), ("谷", "09-23 18:00", "09-24 09:00"))
check("00:10 属前一日 18:00 起的空闲段",
      state(2026, 9, 23, 0, 10), ("谷", "09-22 18:00", "09-23 09:00"))

section("2. 周末整天空闲（并与周五晚间接成一片）")
check("周六 10:00 属空闲段", state(2026, 9, 19, 10, 0)[0], "谷")
check("周五 18:00 -> 下周一 09:00 连成一整段",
      state(2026, 9, 19, 10, 0), ("谷", "09-18 18:00", "09-21 09:00"))
check("周日 23:59 仍空闲", state(2026, 9, 20, 23, 59)[0], "谷")
check("周六整天算全天空闲", is_all_day_valley(date(2026, 9, 19)), True)

section("3. 法定节假日整天空闲")
check("中秋 09-25（周五）10:00 属空闲段", state(2026, 9, 25, 10, 0)[0], "谷")
check("国庆 10-01（周四）15:00 属空闲段", state(2026, 10, 1, 15, 0)[0], "谷")
check("调休补班的周日 01-04 仍按周末空闲", state(2026, 1, 4, 10, 0)[0], "谷")
check("2026 年共 33 天法定节假日", len(ACTIVE["holidays"]), 33)
check("09-23 不是节假日", is_all_day_valley(date(2026, 9, 23)), False)

section("4. 关键合并：周四 18:00 -> 假期+周末 -> 下周一 09:00")
check("09-24（周四）20:00 起连成一段到 09-28（周一）09:00",
      state(2026, 9, 24, 20, 0), ("谷", "09-24 18:00", "09-28 09:00"))
check("09-25 中秋当天同属这一整段",
      state(2026, 9, 25, 10, 0), ("谷", "09-24 18:00", "09-28 09:00"))
check("09-27（周日）深夜仍在同一段",
      state(2026, 9, 27, 23, 59), ("谷", "09-24 18:00", "09-28 09:00"))
check("09-28（周一）09:00 恢复高峰",
      state(2026, 9, 28, 9, 30), ("峰", "09-28 09:00", "09-28 12:00"))
check("单日空闲区间是高峰的补集",
      [(f"{s:%m-%d %H:%M}", f"{e:%m-%d %H:%M}") for s, e in valley_intervals(date(2026, 9, 23))],
      [("09-23 00:00", "09-23 09:00"), ("09-23 12:00", "09-23 14:00"),
       ("09-23 18:00", "09-24 00:00")])

section("5. 交接班预告")
check("09-24 16:00 起接下来 3 次交接班",
      [(f"{t:%m-%d %H:%M}", "梁文谷" if s else "梁文峰")
       for t, s in upcoming_switches(at(2026, 9, 24, 16, 0), 3)],
      [("09-24 18:00", "梁文谷"), ("09-28 09:00", "梁文峰"), ("09-28 12:00", "梁文谷")])
check("普通工作日也能稳定给出 3 条预告",
      len(upcoming_switches(at(2026, 9, 23, 15, 0), 3)), 3)
check("交接时间显示：今天 / 明天 / 后天",
      [fmt_switch_time(at(2026, 9, 23, 18, 0), at(2026, 9, 23, 10, 0)),
       fmt_switch_time(at(2026, 9, 24, 9, 0), at(2026, 9, 23, 10, 0)),
       fmt_switch_time(at(2026, 9, 25, 9, 0), at(2026, 9, 23, 10, 0)),
       fmt_switch_time(at(2026, 9, 30, 9, 0), at(2026, 9, 23, 10, 0))],
      ["今天 18:00", "明天 09:00", "后天 09:00", "09-30 09:00"])

section("6. 值班表文字与时长格式化")
check("工作日值班表", day_schedule_text(date(2026, 9, 23)),
      "高峰 09:00-12:00、14:00-18:00 梁文峰 · 其余时段 梁文谷")
check("节假日值班表", day_schedule_text(date(2026, 9, 25)),
      "全天 梁文谷 · 空闲价（法定节假日）")
check("周末值班表", day_schedule_text(date(2026, 9, 19)),
      "全天 梁文谷 · 空闲价（周末）")
check("fmt_delta", fmt_delta(timedelta(hours=2, minutes=3, seconds=9)), "02:03:09")
check("fmt_delta 跨天", fmt_delta(timedelta(days=3, hours=12, minutes=45)),
      "3天 12:45:00")
check("fmt_delta 负数归零", fmt_delta(timedelta(seconds=-5)), "00:00:00")
check("human_delta 天", human_delta(timedelta(days=3, hours=12, minutes=45)),
      "3 天 12 小时")
check("human_delta 小时+分", human_delta(timedelta(hours=3, minutes=7)), "3 小时 7 分")
check("human_delta 分", human_delta(timedelta(minutes=42)), "42 分")
check("human_delta 秒", human_delta(timedelta(seconds=30)), "不到 1 分钟")
check("WEEKDAYS 从周一开始", WEEKDAYS[0], "周一")

section("7. 运行期开关：周末/节假日不再整天空闲")
RUNTIME["weekend_holiday_as_valley"] = False
check("节假日 09-25 10:00 变成高峰", state(2026, 9, 25, 10, 0)[0], "峰")
check("节假日 09-25 12:30 仍是空闲", state(2026, 9, 25, 12, 30)[0], "谷")
check("节假日 09-25 20:00 仍是空闲", state(2026, 9, 25, 20, 0)[0], "谷")
check("周六 10:00 仍不算高峰（高峰只限工作日）",
      state(2026, 9, 19, 10, 0)[0], "谷")
RUNTIME["weekend_holiday_as_valley"] = True
check("开关恢复后 节假日 09-25 10:00 又是空闲", state(2026, 9, 25, 10, 0)[0], "谷")

section("8. 规则 payload 与缓存往返")
saved = dict(ACTIVE)
try:
    payload = default_rules()
    payload.update({
        "peak_windows": [(dtime(10, 0), dtime(11, 0))],
        "peak_workday_only": True,
        "weekend_valley": False,
        "holidays": ["2026-03-03"],
        "models": DEFAULT_MODELS,
        "origin": "live",
        "source": "https://example.invalid/pricing",
        "fetched_at": "2026-03-01 08:00:00",
        "holiday_years": [2026],
    })
    R.CACHE_NAME = ".selftest_cache.json"
    save_cache(payload)
    os.path.exists(R.cache_path()) or (_ for _ in ()).throw(AssertionError("缓存没写出来"))
    check("缓存文件写到了程序目录", os.path.dirname(R.cache_path()), app_dir())

    apply_payload(payload)
    check("apply_payload 覆盖了高峰窗口", peak_windows(), [(dtime(10, 0), dtime(11, 0))])
    check("apply_payload 覆盖了节假日", ACTIVE["holidays"], {date(2026, 3, 3)})
    check("apply_payload 记下了来源", ACTIVE["origin"], "live")
    check("apply_payload 关掉了周末整天空闲", ACTIVE["weekend_valley"], False)
    check("开关停机时间跟着 payload 走", RUNTIME["weekend_holiday_as_valley"], False)
    check("2026-03-03 现在算高峰日（周末规则已关）",
          is_all_day_valley(date(2026, 3, 3)), False)

    loaded = load_cache()
    check("缓存能读回来", bool(loaded and loaded.get("models")), True)
    check("读回来时来源标记为 cache", (loaded or {}).get("origin"), "cache")
    check("JSON 序列化不报错", "peak_windows" in payload_to_json(payload), True)
finally:
    try:
        os.remove(R.cache_path())
    except OSError:
        pass
    R.CACHE_NAME = ".deepseek_peak_clock_cache.json"
    ACTIVE.clear()
    ACTIVE.update(saved)
    RUNTIME["weekend_holiday_as_valley"] = saved["weekend_valley"]
    check("测试后规则已还原", peak_windows(),
          [(dtime(9, 0), dtime(12, 0)), (dtime(14, 0), dtime(18, 0))])

section("9. 定价页解析")
SAMPLE = """
<html><body>
<p>北京时间周一至周五 09:00-12:00、14:00-18:00 为高峰时段，其余时段为空闲时段，
   周末与法定节假日全天也算空闲时段。</p>
<p>模型 deepseek-flash、deepseek-v4-pro BASEURL https://api.deepseek.com</p>
<p>百万tokens输入（缓存命中）空闲时段0.02元0.03元高峰时段0.04元0.06元</p>
<p>百万tokens输入（缓存未命中）空闲时段1元1.5元高峰时段2元3元</p>
<p>百万tokens输出空闲时段4元6元高峰时段8元12元</p>
</body></html>
"""
parsed = parse_pricing_page(SAMPLE)
check("解析出两段高峰窗口", parsed["peak_windows"],
      [(dtime(9, 0), dtime(12, 0)), (dtime(14, 0), dtime(18, 0))])
check("识别为「仅周一至周五」", parsed["peak_workday_only"], True)
check("识别出周末也算空闲", parsed["weekend_valley"], True)
check("解析出两个模型", [m["name"] for m in parsed["models"]],
      ["deepseek-flash", "deepseek-v4-pro"])
check("缓存命中价按模型顺序落到各自身上",
      [m["idle"]["缓存命中输入"] for m in parsed["models"]], [0.02, 0.03])
check("输出价解析正确",
      [m["peak"]["输出"] for m in parsed["models"]], [8.0, 12.0])
check("整数字面量也能解析",
      [m["peak"]["缓存未命中输入"] for m in parsed["models"]], [2.0, 3.0])
check("去标签后不含尖括号", "<" in _strip_html(SAMPLE), False)
check("_squash 去掉所有空白", _squash("a b  c"), "abc")
try:
    parse_pricing_page("<html>完全没有价格信息</html>")
    check("解析失败时会抛异常", False, True)
except Exception as exc:
    check("解析失败时会抛异常", type(exc).__name__, "ValueError")

section("10. 路径处理（源码运行与打包运行都要对）")
import sys as _sys                                                # noqa: E402
from core.paths import is_frozen                                  # noqa: E402

print(f"  （当前：{'打包 exe' if is_frozen() else '源码'} 方式运行）")
if is_frozen():
    check("打包后 app_dir 就是 exe 所在目录", app_dir(),
          os.path.dirname(os.path.abspath(_sys.executable)))
else:
    check("源码运行时 app_dir 指向项目根", os.path.basename(app_dir()),
          "DeepseekPeakClock")
check("app_path 一定拼在 app_dir 下", os.path.dirname(app_path("x.json")), app_dir())
check("assets 作为随包资源能定位到", os.path.isdir(resource_path("assets")), True)
print(f"        图标：{icon_path() or '(没找到)'}")
check("图标资源真实存在", bool(icon_path()) and os.path.exists(icon_path()), True)
print(f"        缓存：{R.cache_path()}")
check("缓存文件也落在可写目录里",
      os.path.dirname(R.cache_path()) in (app_dir(), os.path.expanduser("~")), True)

section("11. 用「现在」实跑一遍")
now = now_beijing()
off, start, end = current_period(now)
print(f"  现在（北京）: {now:%Y-%m-%d %H:%M:%S %Z}  {WEEKDAYS[now.weekday()]}")
print(f"  当前值班    : {'梁文谷（空闲）' if off else '梁文峰（高峰）'}")
print(f"  本段区间    : {start:%m-%d %H:%M} -> {end:%m-%d %H:%M}"
      f"  剩 {fmt_delta(end - now)}")
print(f"  今日值班    : {day_schedule_text(now.date())}")
check("当前时段起点早于终点", start < end, True)
check("当前时刻落在本段区间内", start <= now < end, True)

print(f"\n{'=' * 62}")
if FAILS:
    print(f"=== {len(FAILS)} FAILED ===")
    for f in FAILS:
        print(f"  - {f}")
else:
    print("=== ALL PASS ===")
sys.exit(1 if FAILS else 0)
