# -*- coding: utf-8 -*-
"""
界面层自检
==========

离屏跑（QT_QPA_PLATFORM=offscreen），不联网、不写真实设置：
把主窗口搭起来、跑几遍 tick()、切一次主题、走一遍设置往返与托盘逻辑。

    python selftest_ui.py
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PyQt5.QtCore import QSettings, Qt                            # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel                  # noqa: E402

# 设置写到临时 ini，别污染注册表里用户真实的配置
_TMP_CFG = tempfile.mkdtemp(prefix="peakclock_cfg_")
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _TMP_CFG)

app = QApplication.instance() or QApplication(sys.argv)

from core import rules as R                                       # noqa: E402
from core.config import APP_ORG                                   # noqa: E402
from core.rules import ACTIVE, RUNTIME, default_rules             # noqa: E402
from theme import QSS                                             # noqa: E402
from ui.widgets import Card, DayTimeline, make_icon               # noqa: E402
from ui.window import PeakClockWindow                             # noqa: E402

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


def ok(label: str, cond, detail="") -> None:
    check(label + (f"   [{detail}]" if detail else ""), bool(cond), True)


section("1. 主窗口能搭起来")
win = PeakClockWindow()
win.chk_auto.setChecked(False)          # 免得 1.2 秒后自己联网
win.show()
app.processEvents()

for name in ("lbl_clock", "lbl_duty", "lbl_name", "lbl_cd", "lbl_progress", "bar",
             "lbl_beijing", "lbl_date", "lbl_tz", "timeline", "lbl_next",
             "lbl_schedule", "lbl_source", "price_holder", "chk_notify",
             "chk_weekend", "spin_lead", "btn_reload", "btn_hide", "btn_quit",
             "lbl_banner", "lbl_badge", "lbl_slogan"):
    ok(f"控件存在：{name}", getattr(win, name, None) is not None)
ok("窗口标题带了应用名", "峰谷时钟" in win.windowTitle(), win.windowTitle())
ok("主样式表已应用", win.styleSheet() == QSS)
ok("只有一个 QApplication（没有重复创建）", QApplication.instance() is app)

section("2. tick() 每秒跑一遍")
before = win.lbl_clock.text()
win.tick()
app.processEvents()
after = win.lbl_clock.text()
ok("时钟文本是 HH:MM:SS", len(after) == 8 and after.count(":") == 2, after)
ok("秒数在 0-59", 0 <= int(after.split(":")[2]) <= 59, after)
ok("当前值班只有两种取值", win.lbl_name.text() in ("梁文峰", "梁文谷"), win.lbl_name.text())
ok("倒计时是 mm:ss 或 hh:mm:ss",
   win.lbl_cd.text().count(":") in (1, 2) or "天" in win.lbl_cd.text(),
   win.lbl_cd.text())
ok("进度条在量程内", win.bar.minimum() <= win.bar.value() <= win.bar.maximum(),
   f"{win.bar.value()}/{win.bar.maximum()}")
ok("北京时间和本地时间都填上了",
   bool(win.lbl_beijing.text()) and bool(win.lbl_date.text()))
ok("交接班预告有 3 条", win.lbl_next.text().count("→") == 3, win.lbl_next.text())

for _ in range(3):
    win.tick()
    app.processEvents()
ok("连续 tick 不出错", True)

section("3. 主题随峰谷切换")
win._off = None
win._styled_off = None
win._apply_theme(False)
app.processEvents()
peak_qss = win._hero.styleSheet()
peak_name = win.lbl_name.styleSheet()
win._apply_theme(True)
app.processEvents()
valley_qss = win._hero.styleSheet()
valley_name = win.lbl_name.styleSheet()
ok("高峰与空闲的 Hero 渐变不同", peak_qss != valley_qss)
ok("高峰与空闲的名字配色不同", peak_name != valley_name)
ok("高峰 Hero 用了暖色", "#FF" in peak_qss.upper() or "255" in peak_qss, peak_qss[:40])
ok("空闲 Hero 用了冷色", "#D8FB" in valley_qss.upper() or "216" in valley_qss,
   valley_qss[:40])
timeline = win.timeline
ok("时间轴是自绘控件", isinstance(timeline, DayTimeline))

section("4. 时间轴能画出来")
timeline.resize(600, timeline.minimumHeight())
timeline.refresh()
app.processEvents()
shot = timeline.grab()
ok("时间轴渲染出非空图像", not shot.isNull() and shot.width() > 100,
   f"{shot.width()}x{shot.height()}")

section("5. 托盘图标")
off_icon = make_icon(True)
peak_icon = make_icon(False)
ok("空闲图标非空", not off_icon.isNull() and not off_icon.pixmap(64, 64).isNull())
ok("高峰图标非空", not peak_icon.isNull() and not peak_icon.pixmap(64, 64).isNull())
ok("两种状态图标不同",
   off_icon.pixmap(64, 64).toImage() != peak_icon.pixmap(64, 64).toImage())
ok("卡片控件是 QFrame 子类", isinstance(Card(), Card))

section("6. 周末开关真的改到引擎")
snapshot = RUNTIME["weekend_holiday_as_valley"]
win.chk_weekend.setChecked(not snapshot)
app.processEvents()
from datetime import date                                        # noqa: E402
from core.engine import is_all_day_valley                        # noqa: E402
check("关掉周末整天空闲后开关跟着变",
      RUNTIME["weekend_holiday_as_valley"], not snapshot)
check("关掉后周六不再算全天空闲", is_all_day_valley(date(2026, 9, 19)), False)
win.chk_weekend.setChecked(snapshot)
app.processEvents()
check("勾回来以后周六又算全天空闲", is_all_day_valley(date(2026, 9, 19)), True)

section("7. 置顶开关改窗口标志")
was_top = bool(win.windowFlags() & Qt.WindowStaysOnTopHint)
win.btn_top.setChecked(not was_top)
app.processEvents()
ok("置顶状态被切换", bool(win.windowFlags() & Qt.WindowStaysOnTopHint) != was_top)
win.btn_top.setChecked(was_top)
app.processEvents()
ok("置顶状态能还原", bool(win.windowFlags() & Qt.WindowStaysOnTopHint) == was_top)

section("8. 设置保存 / 恢复往返")
# 换成写在临时 ini 里的 QSettings，别动注册表里用户真实的配置
win.settings = QSettings(QSettings.IniFormat, QSettings.UserScope,
                         APP_ORG, "PeakClockSelftest")
win.settings.clear()
win.settings.sync()

# --- 保存方向 ---
win.spin_lead.setValue(7)
win.chk_lead.setChecked(True)
win.chk_notify.setChecked(True)
win._save_settings()
win.settings.sync()
check("提前提醒分钟数存下来了", win.settings.value("lead_minutes", type=int), 7)
check("提醒开关也存下来了", win.settings.value("notify", type=bool), True)
ok("设置写进了临时 ini（没碰注册表）",
   any(f.endswith(".ini") for _, _, fs in os.walk(_TMP_CFG) for f in fs),
   str(os.listdir(_TMP_CFG)))

# --- 恢复方向：直接改 ini，再看控件有没有跟着回来 ---
# （不能先改控件：改控件会立刻自动保存，把 ini 覆盖掉）
win.settings.setValue("lead_minutes", 23)
win.settings.setValue("notify", False)
win.settings.setValue("lead_enabled", False)
win.settings.sync()
win._restore_settings()
check("恢复后提前提醒分钟数变成 23", win.spin_lead.value(), 23)
check("恢复后提醒开关跟着取消勾选", win.chk_notify.isChecked(), False)
check("恢复后提前提醒输入框被禁用", win.spin_lead.isEnabled(), False)

win.settings.clear()
win.settings.sync()
win._restore_settings()
check("ini 清空后回落到默认的 10 分钟", win.spin_lead.value(), 10)
check("ini 清空后默认开着提醒", win.chk_notify.isChecked(), True)

section("9. 规则回填与联网失败")
saved = dict(ACTIVE)
old_cache = R.CACHE_NAME
try:
    R.CACHE_NAME = ".selftest_ui_cache.json"
    payload = default_rules()
    # 走真实路径：联网/缓存里的节假日是 ISO 字符串，不是 date 对象
    payload["holidays"] = sorted(d.isoformat() for d in payload["holidays"])
    payload.update({"origin": "live", "source": "https://example.invalid",
                    "fetched_at": "2026-03-01 08:00:00", "holiday_years": [2026]})
    win._on_rules_ready(payload)
    app.processEvents()
    ok("回填后来源行显示已更新", "已从官网更新" in win.lbl_source.text(),
       win.lbl_source.text()[:60])
    ok("回填后价格表重建过", win.price_holder is not None)
    ok("回填后没有残留错误", win._last_error == "", win._last_error)

    win._on_rules_failed("测试用的失败")
    app.processEvents()
    ok("联网失败会记下来", win._last_error == "测试用的失败", win._last_error)
    ok("失败时来源行给出提示", "失败" in win.lbl_source.text() or "内置" in win.lbl_source.text(),
       win.lbl_source.text()[:60])

    win._on_fetch_finished()
    ok("更新按钮恢复可用", win.btn_reload.isEnabled(), True)
finally:
    try:
        os.remove(R.cache_path())
    except OSError:
        pass
    R.CACHE_NAME = old_cache
    ACTIVE.clear()
    ACTIVE.update(saved)

section("10. 隐藏到托盘 / 重新显示")
from PyQt5.QtWidgets import QSystemTrayIcon                       # noqa: E402
has_tray = QSystemTrayIcon.isSystemTrayAvailable()
print(f"  （本机托盘可用：{has_tray}；离屏环境通常为 False，"
      f"此时 _build_tray 会直接返回，托盘相关控件不存在）")
check("托盘不可用时 win.tray 为 None", win.tray is None, not has_tray)
check("托盘不可用时也不会建出托盘菜单", hasattr(win, "act_top"), has_tray)
win._hide_to_tray()
app.processEvents()
if has_tray:
    ok("隐藏后窗口不可见", not win.isVisible())
    win._show_window()
    app.processEvents()
    ok("能重新显示出来", win.isVisible())
else:
    ok("没有托盘时隐藏是空操作，窗口仍在", win.isVisible())
win.chk_notify.setChecked(False)
win.notify(switch_to_off=True)
win.notify(switch_to_off=False)
ok("关掉提醒后 notify 不弹也不报错", True)

section("11. 价格表随模型数重建")
labels = win._price_host.findChildren(QLabel) if win._price_host else []
check("价格表里的价格标签数 = 模型数 × 指标数 × 2",
      (len(win.price_idle_labels), len(win.price_peak_labels)),
      (len(ACTIVE["models"]) * 3, len(ACTIVE["models"]) * 3))
ok("价格表里有标签", len(labels) >= len(ACTIVE["models"]) * 6, f"{len(labels)} 个")
ok("模型数至少 1", len(ACTIVE["models"]) >= 1, str(len(ACTIVE["models"])))
ok("每个模型都有空闲价与高峰价",
   all(m.get("idle") and m.get("peak") for m in ACTIVE["models"]), True)
check("空闲价表里不是横杠（内置默认值完整）",
      any(t.text() != "—" for t in win.price_idle_labels), True)

section("12. 收尾")
RUNTIME["weekend_holiday_as_valley"] = ACTIVE["weekend_valley"]
win.timer.stop()
win.auto_timer.stop()
win._quit()
app.processEvents()
ok("退出前计时器已停", not win.timer.isActive())

print(f"\n{'=' * 62}")
if FAILS:
    print(f"=== {len(FAILS)} FAILED ===")
    for f in FAILS:
        print(f"  - {f}")
else:
    print("=== ALL PASS ===")

try:
    import shutil
    shutil.rmtree(_TMP_CFG, ignore_errors=True)
except Exception:
    pass

sys.exit(1 if FAILS else 0)
