# -*- coding: utf-8 -*-
"""主窗口
======

一屏放下四块：值班大字卡、时钟卡、价格对照表、提醒设置。
整卡配色跟着峰谷状态走，托盘常驻，交接班时弹通知。
"""

from __future__ import annotations
from datetime import datetime, timedelta
from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton,
                             QScrollArea, QSpinBox, QSystemTrayIcon, QVBoxLayout,
                             QWidget)
from core.config import APP_NAME, APP_ORG, APP_TITLE, APP_VERSION
from core.engine import (WEEKDAYS, current_period, day_schedule_text, fmt_delta,
                         fmt_switch_time, human_delta, upcoming_switches)
from core.rules import (ACTIVE, RUNTIME, apply_payload, load_cache, save_cache)
from theme import QSS
from ui.fetch import RulesFetcher
from ui.widgets import Card, DayTimeline, make_icon
from core.config import METRICS, now_beijing
from core.rules import default_rules
from theme import C_MINT, C_MINT_SOFT, C_OK, C_PINK, C_PINK_SOFT, C_PURPLE, C_TEXT, C_TEXT_DIM, C_WARN


class PeakClockWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle(APP_TITLE)
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.resize(700, 920)

        self.settings = QSettings(APP_ORG, APP_NAME)

        self._off: bool | None = None
        self._styled_off: bool | None = None
        self._lead_fired = False
        self._tray_hinted = False
        self._loading = True
        self._last_error = ""
        self._price_host: QWidget | None = None
        self._fetcher: RulesFetcher | None = None
        self.tray: QSystemTrayIcon | None = None

        # 先吃缓存（有就用缓存，没有就是内置默认），保证界面立刻可用
        cached = load_cache()
        if cached:
            try:
                apply_payload(cached)
            except Exception as exc:
                self._last_error = f"缓存解析失败：{exc}"
                apply_payload(default_rules())

        self._build_ui()
        self._build_tray()
        self._rebuild_price_table()

        # 定时器必须先建好：_restore_settings() 里 setChecked 会触发 toggled，
        # 而槽函数会去 start() 这两个 QTimer。
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(lambda: self.refresh_rules(manual=False))

        self._restore_settings()

        # 自动更新：启动 1.2 秒后先拉一次，之后按设置的间隔拉
        self._apply_auto_timer()
        QTimer.singleShot(1200, lambda: self.refresh_rules(manual=False))

        self.tick(initial=True)
        self._update_source_line("init")

    # ------------------------- 界面搭建 -------------------------

    def _build_ui(self):
        self.setStyleSheet(QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)

        content = QWidget()
        content.setAutoFillBackground(False)
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        root.addWidget(self._build_header())
        root.addWidget(self._build_hero())
        root.addWidget(self._build_clock_card())
        root.addWidget(self._build_price_card())
        root.addWidget(self._build_reminder_card())
        root.addWidget(self._build_footer())
        root.addStretch(1)

    def _build_header(self) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("DeepSeek 峰谷时钟")
        title.setObjectName("H1")
        sub = QLabel(f"梁文峰 & 梁文谷 的值班表 · 规则与节假日联网自动更新　v{APP_VERSION}")
        sub.setObjectName("Sub")
        col.addWidget(title)
        col.addWidget(sub)
        lay.addLayout(col)
        lay.addStretch(1)

        self.btn_top = QPushButton("置顶")
        self.btn_top.setObjectName("Pill")
        self.btn_top.setCheckable(True)
        self.btn_top.setCursor(Qt.PointingHandCursor)
        self.btn_top.setToolTip("让窗口始终保持在最前面")
        self.btn_top.toggled.connect(self._on_top_toggled)
        lay.addWidget(self.btn_top)

        self.btn_hide = QPushButton("收进托盘")
        self.btn_hide.setObjectName("Pill")
        self.btn_hide.setCursor(Qt.PointingHandCursor)
        self.btn_hide.setToolTip("隐藏到系统托盘，后台继续提醒")
        self.btn_hide.clicked.connect(self._hide_to_tray)
        lay.addWidget(self.btn_hide)

        return box

    def _build_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("Hero")
        lay = QVBoxLayout(hero)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_duty = QLabel("现在值班的是")
        self.lbl_duty.setObjectName("Dim")
        top.addWidget(self.lbl_duty)
        top.addStretch(1)
        self.lbl_badge = QLabel("—")
        self.lbl_badge.setObjectName("Tag")
        top.addWidget(self.lbl_badge)
        lay.addLayout(top)

        self.lbl_name = QLabel("—")
        self.lbl_name.setObjectName("HeroName")
        lay.addWidget(self.lbl_name)

        self.lbl_slogan = QLabel("—")
        self.lbl_slogan.setObjectName("Date")
        self.lbl_slogan.setWordWrap(True)
        lay.addWidget(self.lbl_slogan)

        lay.addSpacing(4)

        cd_row = QHBoxLayout()
        cd_row.setSpacing(8)
        self.lbl_cd_prefix = QLabel("距 下一次交接班 还有")
        self.lbl_cd_prefix.setObjectName("Dim")
        self.lbl_cd = QLabel("--:--:--")
        self.lbl_cd.setObjectName("Countdown")
        cd_row.addWidget(self.lbl_cd_prefix)
        cd_row.addWidget(self.lbl_cd)
        cd_row.addStretch(1)
        self.lbl_cd_when = QLabel("")
        self.lbl_cd_when.setObjectName("Dim")
        cd_row.addWidget(self.lbl_cd_when)
        lay.addLayout(cd_row)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        lay.addWidget(self.bar)

        self.lbl_progress = QLabel("本时段进度 —")
        self.lbl_progress.setObjectName("Dim")
        lay.addWidget(self.lbl_progress)

        self._hero = hero
        return hero

    def _build_clock_card(self) -> QWidget:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("🕒 本地时间与峰谷时间轴")
        t.setObjectName("CardT")
        head.addWidget(t)
        head.addStretch(1)
        self.lbl_tz = QLabel("—")
        self.lbl_tz.setObjectName("Dim")
        head.addWidget(self.lbl_tz)
        lay.addLayout(head)

        self.lbl_clock = QLabel("--:--:--")
        self.lbl_clock.setObjectName("Clock")
        lay.addWidget(self.lbl_clock)

        self.lbl_date = QLabel("—")
        self.lbl_date.setObjectName("Date")
        lay.addWidget(self.lbl_date)

        self.lbl_beijing = QLabel("—")
        self.lbl_beijing.setObjectName("Dim")
        lay.addWidget(self.lbl_beijing)

        lay.addSpacing(4)
        self.timeline = DayTimeline()
        lay.addWidget(self.timeline)

        legend = QHBoxLayout()
        legend.setSpacing(14)
        for text, color in (("梁文谷 · 空闲时段", C_MINT),
                            ("梁文峰 · 高峰时段", C_PINK),
                            ("现在（北京时间）", C_PURPLE)):
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color}; font-size:10pt;")
            lab = QLabel(text)
            lab.setObjectName("Dim")
            row = QHBoxLayout()
            row.setSpacing(4)
            row.addWidget(dot)
            row.addWidget(lab)
            legend.addLayout(row)
        legend.addStretch(1)
        lay.addLayout(legend)

        self.lbl_schedule = QLabel("今日值班：—")
        self.lbl_schedule.setObjectName("Dim")
        self.lbl_schedule.setWordWrap(True)
        lay.addWidget(self.lbl_schedule)

        self.lbl_next = QLabel("接下来：—")
        self.lbl_next.setObjectName("Dim")
        self.lbl_next.setWordWrap(True)
        lay.addWidget(self.lbl_next)

        return card

    def _build_price_card(self) -> QWidget:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel("💸 模型价格（元 / 百万 tokens）")
        t.setObjectName("CardT")
        head.addWidget(t)
        head.addStretch(1)
        self.btn_reload = QPushButton("🔄 立即更新")
        self.btn_reload.setObjectName("Pill")
        self.btn_reload.setCursor(Qt.PointingHandCursor)
        self.btn_reload.setToolTip("立刻联网获取最新的峰谷时段、价格与节假日")
        self.btn_reload.clicked.connect(lambda: self.refresh_rules(manual=True))
        head.addWidget(self.btn_reload)
        lay.addLayout(head)

        # 价格表容器：每次拿到新数据就整块重建
        self.price_holder = QVBoxLayout()
        self.price_holder.setContentsMargins(0, 0, 0, 0)
        self.price_holder.setSpacing(0)
        lay.addLayout(self.price_holder)

        self.lbl_source = QLabel("数据源：—")
        self.lbl_source.setObjectName("Dim")
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setTextFormat(Qt.RichText)
        lay.addWidget(self.lbl_source)

        opt = QHBoxLayout()
        opt.setSpacing(10)
        self.chk_auto = QCheckBox("启动时自动联网更新")
        self.chk_auto.setCursor(Qt.PointingHandCursor)
        self.lbl_every = QLabel("间隔")
        self.lbl_every.setObjectName("Dim")
        self.spin_every = QSpinBox()
        self.spin_every.setRange(1, 72)
        self.spin_every.setSuffix(" 小时")
        self.spin_every.setToolTip("每隔多久自动重新获取一次规则与价格")
        opt.addWidget(self.chk_auto)
        opt.addSpacing(6)
        opt.addWidget(self.lbl_every)
        opt.addWidget(self.spin_every)
        opt.addStretch(1)
        lay.addLayout(opt)

        self.chk_auto.toggled.connect(self._on_auto_changed)
        self.spin_every.valueChanged.connect(self._on_auto_changed)

        return card

    def _build_price_table(self) -> QWidget:
        """按当前生效的规则渲染价格表（模型数量不固定，所以动态构建）。"""
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.price_idle_labels: list[QLabel] = []
        self.price_peak_labels: list[QLabel] = []

        models = ACTIVE["models"]
        ratio = 0.5
        for m in models:
            pk = m["peak"].get("输出")
            idl = m["idle"].get("输出")
            if pk and idl:
                ratio = idl / pk
                break

        for m in models:
            row_head = QHBoxLayout()
            nm = QLabel(m["name"])
            nm.setStyleSheet(f"color:{C_TEXT}; font-size:10.5pt; font-weight:700;")
            tag = QLabel(f"空闲价 = 高峰 × {ratio:g}")
            tag.setObjectName("Tag")
            row_head.addWidget(nm)
            row_head.addStretch(1)
            row_head.addWidget(tag)
            lay.addLayout(row_head)

            grid = QGridLayout()
            grid.setContentsMargins(6, 0, 0, 0)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(3)
            for col, txt in enumerate(["项目", "空闲时段", "", "高峰时段"]):
                h = QLabel(txt)
                h.setObjectName("Dim")
                if col in (1, 3):
                    h.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                grid.addWidget(h, 0, col)

            for r, metric in enumerate(METRICS, start=1):
                lab = QLabel(metric)
                lab.setObjectName("Dim")
                iv = m["idle"].get(metric)
                pv = m["peak"].get(metric)
                li = QLabel("—" if iv is None else f"{iv:g}")
                lp = QLabel("—" if pv is None else f"{pv:g}")
                arrow = QLabel("→")
                arrow.setObjectName("Dim")
                for x in (li, lp):
                    x.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    x.setObjectName("Mono")
                self.price_idle_labels.append(li)
                self.price_peak_labels.append(lp)
                grid.addWidget(lab, r, 0)
                grid.addWidget(li, r, 1)
                grid.addWidget(arrow, r, 2)
                grid.addWidget(lp, r, 3)

            grid.setColumnStretch(0, 1)
            lay.addLayout(grid)

            if m is not models[-1]:
                line = QFrame()
                line.setObjectName("Line")
                lay.addWidget(line)

        note = QLabel("注：单价随官方调整，本表由定价页自动解析；"
                      "解析失败时会退回缓存或内置默认值。")
        note.setObjectName("Dim")
        note.setWordWrap(True)
        lay.addWidget(note)
        return host

    def _rebuild_price_table(self):
        if self._price_host is not None:
            self.price_holder.removeWidget(self._price_host)
            self._price_host.setParent(None)
            self._price_host.deleteLater()
        self._price_host = self._build_price_table()
        self.price_holder.addWidget(self._price_host)
        if self._styled_off is not None:
            self._apply_theme(self._styled_off)

    def _build_reminder_card(self) -> QWidget:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel("🔔 提醒设置")
        t.setObjectName("CardT")
        head.addWidget(t)
        head.addStretch(1)
        self.lbl_notify_state = QLabel("—")
        self.lbl_notify_state.setObjectName("Dim")
        head.addWidget(self.lbl_notify_state)
        lay.addLayout(head)

        self.chk_notify = QCheckBox("交接班时弹桌面通知（托盘气泡）")
        self.chk_sound = QCheckBox("同时响一下提示音")
        self.chk_weekend = QCheckBox("周末 / 法定节假日整天按空闲时段计（官方规则）")
        self.chk_tray = QCheckBox("点关闭时最小化到托盘而不是退出")
        for c in (self.chk_notify, self.chk_sound, self.chk_weekend, self.chk_tray):
            c.setCursor(Qt.PointingHandCursor)
            lay.addWidget(c)

        lead_row = QHBoxLayout()
        lead_row.setSpacing(8)
        self.chk_lead = QCheckBox("空闲时段开始前")
        self.chk_lead.setCursor(Qt.PointingHandCursor)
        self.spin_lead = QSpinBox()
        self.spin_lead.setRange(0, 60)
        self.spin_lead.setSuffix(" 分钟")
        self.spin_lead.setToolTip("0 表示不提前提醒；建议 5~15 分钟")
        lab_tail = QLabel("先提醒我一次")
        lab_tail.setObjectName("Dim")
        lead_row.addWidget(self.chk_lead)
        lead_row.addWidget(self.spin_lead)
        lead_row.addWidget(lab_tail)
        lead_row.addStretch(1)
        lay.addLayout(lead_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_test = QPushButton("测试提醒")
        self.btn_test.setObjectName("Pill")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.clicked.connect(lambda: self.notify(force=True, test=True))
        self.btn_refresh = QPushButton("立即刷新界面")
        self.btn_refresh.setObjectName("Pill")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(lambda: self.tick())
        self.btn_quit = QPushButton("退出")
        self.btn_quit.setObjectName("Pill")
        self.btn_quit.setCursor(Qt.PointingHandCursor)
        self.btn_quit.clicked.connect(self._quit)
        btn_row.addWidget(self.btn_test)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_quit)
        lay.addLayout(btn_row)

        self.lbl_banner = QLabel("等待状态……")
        self.lbl_banner.setObjectName("Banner")
        self.lbl_banner.setWordWrap(True)
        lay.addWidget(self.lbl_banner)

        self.chk_notify.toggled.connect(self._on_setting_changed)
        self.chk_sound.toggled.connect(self._on_setting_changed)
        self.chk_tray.toggled.connect(self._on_setting_changed)
        self.chk_weekend.toggled.connect(self._on_weekend_toggled)
        self.chk_lead.toggled.connect(self._on_setting_changed)
        self.spin_lead.valueChanged.connect(self._on_lead_changed)

        return card

    def _build_footer(self) -> QWidget:
        lab = QLabel(
            "时段规则：北京时间<b>周一至周五（不含中国法定节假日）9:00-12:00、14:00-18:00</b> 为高峰时段；"
            "其余时段，含周末及法定节假日全天，均为空闲时段（空闲价 = 高峰价的一半）。"
            "<br>规则/价格自动取自 "
            "<a href='https://api-docs.deepseek.com/zh-cn/quick_start/pricing'>DeepSeek 官方定价页</a>，"
            "节假日取自公开节假日接口；如与官网不一致，请以官网为准。"
        )
        lab.setObjectName("Dim")
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.RichText)
        lab.setOpenExternalLinks(True)
        return lab

    # ------------------------- 联网更新 -------------------------

    def refresh_rules(self, manual: bool = False):
        if self._fetcher is not None and self._fetcher.isRunning():
            return
        if not manual and not self.chk_auto.isChecked():
            return
        self.btn_reload.setEnabled(False)
        self.btn_reload.setText("⏳ 更新中…")
        self._fetcher = RulesFetcher(self)
        self._fetcher.rules_ready.connect(self._on_rules_ready)
        self._fetcher.rules_failed.connect(self._on_rules_failed)
        self._fetcher.finished.connect(self._on_fetch_finished)
        self._fetcher.start()

    def _on_rules_ready(self, payload: dict):
        try:
            apply_payload(payload)
        except Exception as exc:
            self._last_error = f"解析失败：{exc}"
            return
        save_cache(payload)
        self._last_error = ""
        self.chk_weekend.setChecked(bool(ACTIVE.get("weekend_valley", True)))
        self._rebuild_price_table()
        self.timeline.refresh()
        self._styled_off = None          # 规则变了，强制重设主题
        self.tick()
        self._update_source_line("live")

    def _on_rules_failed(self, msg: str):
        self._last_error = msg
        self._update_source_line("error")

    def _on_fetch_finished(self):
        self.btn_reload.setEnabled(True)
        self.btn_reload.setText("🔄 立即更新")

    def _update_source_line(self, event: str = "init"):
        origin = ACTIVE.get("origin", "builtin")
        years = ACTIVE.get("holiday_years") or []
        n_hol = len(ACTIVE["holidays"])
        if origin == "live":
            head = f"<span style='color:{C_OK}'>✅ 已从官网更新</span>"
        elif origin == "cache":
            head = f"<span style='color:{C_WARN}'>📦 使用本地缓存</span>"
        else:
            head = f"<span style='color:{C_WARN}'>📦 使用内置默认规则</span>"

        ts = ACTIVE.get("fetched_at")
        when = ts.strftime("%m-%d %H:%M") if ts else "从未"
        hol = (f"节假日：{('、'.join(str(y) for y in years))} 共 {n_hol} 天"
               if years else f"节假日：内置 {n_hol} 天（未联网更新）")
        src = "api-docs.deepseek.com" if origin in ("live", "cache") else "内置"

        parts = [head, f"来源：{src}", f"更新于 {when}", hol]
        text = "　·　".join(parts)

        if event == "error" and self._last_error:
            text += f"<br><span style='color:{C_WARN}'>⚠️ 本次联网失败：{self._last_error[:160]}</span>"
        elif ACTIVE.get("holiday_error") and origin == "live":
            text += f"<br><span style='color:{C_WARN}'>⚠️ 部分节假日源不可用：{str(ACTIVE['holiday_error'])[:120]}</span>"
        self.lbl_source.setText(text)

    def _on_auto_changed(self, *_):
        self._apply_auto_timer()
        if self._loading:
            return
        self._save_settings()

    def _apply_auto_timer(self):
        if self.chk_auto.isChecked():
            self.auto_timer.start(max(1, self.spin_every.value()) * 3600 * 1000)
        else:
            self.auto_timer.stop()

    # ------------------------- 托盘 -------------------------

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._icon_valley = make_icon(True)
        self._icon_peak = make_icon(False)
        self.tray = QSystemTrayIcon(self._icon_valley, self)
        self.tray.setToolTip(APP_TITLE)

        # 注意：setContextMenu() 不接管所有权，菜单必须有 parent/引用，否则会被 GC 回收
        menu = QMenu(self)
        self.tray_menu = menu
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self._show_window)
        self.act_top = QAction("窗口置顶", self)
        self.act_top.setCheckable(True)
        self.act_top.toggled.connect(self.btn_top.setChecked)
        act_reload = QAction("立即更新规则", self)
        act_reload.triggered.connect(lambda: self.refresh_rules(manual=True))
        act_test = QAction("测试提醒", self)
        act_test.triggered.connect(lambda: self.notify(force=True, test=True))
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self._quit)

        menu.addAction(act_show)
        menu.addAction(self.act_top)
        menu.addSeparator()
        menu.addAction(act_reload)
        menu.addAction(act_test)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self):
        if self.tray is not None:
            self.hide()
            if not self._tray_hinted:
                self._tray_hinted = True
                self.tray.showMessage(
                    "还在后台盯着",
                    "DeepSeek 峰谷时钟已收进托盘，交接班时会照常提醒你。",
                    QSystemTrayIcon.Information, 5000)
        else:
            self.showMinimized()

    # ------------------------- 设置持久化 -------------------------

    def _restore_settings(self):
        # 下面每个 setChecked/setValue 都会触发槽函数，而槽函数在 _loading
        # 为 False 时会立刻 _save_settings()，把还没读到的那几项覆盖掉。
        # 所以整个恢复过程都要盖住这个开关（初次启动和以后重新恢复都一样）。
        self._loading = True
        s = self.settings
        self.chk_notify.setChecked(s.value("notify", True, type=bool))
        self.chk_sound.setChecked(s.value("sound", True, type=bool))
        self.chk_tray.setChecked(s.value("minimize_to_tray", True, type=bool))
        self.chk_lead.setChecked(s.value("lead_enabled", True, type=bool))
        self.spin_lead.setValue(s.value("lead_minutes", 10, type=int))
        self.chk_auto.setChecked(s.value("auto_refresh", True, type=bool))
        self.spin_every.setValue(s.value("refresh_hours", 6, type=int))

        # 周末/节假日开关：默认跟随官方规则（weekend_valley）
        self.chk_weekend.setChecked(
            s.value("weekend_valley", ACTIVE.get("weekend_valley", True), type=bool))

        top = s.value("always_on_top", False, type=bool)
        self.btn_top.setChecked(top)
        self._apply_top(top)

        geo = s.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        self.spin_lead.setEnabled(self.chk_lead.isChecked())
        RUNTIME["weekend_holiday_as_valley"] = self.chk_weekend.isChecked()
        self._apply_auto_timer()
        self._loading = False

    def _save_settings(self):
        s = self.settings
        s.setValue("notify", self.chk_notify.isChecked())
        s.setValue("sound", self.chk_sound.isChecked())
        s.setValue("weekend_valley", self.chk_weekend.isChecked())
        s.setValue("minimize_to_tray", self.chk_tray.isChecked())
        s.setValue("lead_enabled", self.chk_lead.isChecked())
        s.setValue("lead_minutes", self.spin_lead.value())
        s.setValue("auto_refresh", self.chk_auto.isChecked())
        s.setValue("refresh_hours", self.spin_every.value())
        s.setValue("always_on_top", self.btn_top.isChecked())
        s.setValue("geometry", self.saveGeometry())

    def _on_setting_changed(self, *_):
        self.spin_lead.setEnabled(self.chk_lead.isChecked())
        if self._loading:
            return
        self._save_settings()

    def _on_lead_changed(self, *_):
        self._lead_fired = False
        if self._loading:
            return
        self._save_settings()

    def _on_weekend_toggled(self, checked: bool):
        RUNTIME["weekend_holiday_as_valley"] = checked
        if self._loading:
            return
        self._save_settings()
        self._lead_fired = False
        self.timeline.refresh()
        self.tick()

    def _on_top_toggled(self, checked: bool):
        self._apply_top(checked)
        if getattr(self, "act_top", None) is not None and self.act_top.isChecked() != checked:
            self.act_top.setChecked(checked)
        if self._loading:
            return
        self._save_settings()

    def _apply_top(self, checked: bool):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        if self.isVisible():
            self.show()

    # ------------------------- 每秒心跳 -------------------------

    def tick(self, initial: bool = False):
        now_b = now_beijing()
        now_local = datetime.now().astimezone()
        off, start, end = current_period(now_b)

        # --- 时钟 ---
        self.lbl_clock.setText(now_local.strftime("%H:%M:%S"))
        self.lbl_date.setText(
            f"{now_local.strftime('%Y-%m-%d')}  {WEEKDAYS[now_local.weekday()]}"
        )
        off_hours = now_local.utcoffset()
        sign = "+" if (off_hours or timedelta()).total_seconds() >= 0 else "-"
        tz_secs = abs(int((off_hours or timedelta()).total_seconds()))
        self.lbl_tz.setText(f"本地时区 UTC{sign}{tz_secs // 3600:02d}:{tz_secs % 3600 // 60:02d}")
        if off_hours == timedelta(hours=8):
            self.lbl_beijing.setText(f"北京时间 {now_b.strftime('%H:%M:%S')}（与本地相同）")
        else:
            self.lbl_beijing.setText(
                f"北京时间 {now_b.strftime('%H:%M:%S')}（峰谷判定按北京时间 UTC+8）")

        # --- 倒计时 / 进度 ---
        remaining = end - now_b
        total = (end - start).total_seconds() or 1.0
        done = max(0.0, min(1.0, (now_b - start).total_seconds() / total))
        self.lbl_cd.setText(fmt_delta(remaining))
        self.lbl_progress.setText(
            f"本时段已过 {done * 100:.0f}%　·　{human_delta(remaining)}后交接"
        )

        # --- 值班信息 ---
        next_name = "梁文峰" if off else "梁文谷"
        next_verb = "接班" if off else "上班"
        self.lbl_cd_prefix.setText(f"距 {next_name} {next_verb} 还有")
        self.lbl_cd_when.setText(f"（{fmt_switch_time(end, now_b)}）")
        self.lbl_name.setText("梁文谷" if off else "梁文峰")
        self.lbl_badge.setText("🌙 空闲时段 · 半价" if off else "⚡ 高峰时段 · 标准价")
        if off:
            self.lbl_slogan.setText(
                f"空闲时段单价是高峰的一半，长任务 / 批量任务现在挂上去最划算。"
                f"{human_delta(remaining)}后回到高峰价。")
        else:
            self.lbl_slogan.setText(
                f"高峰时段运行中。不急的活儿建议等 {fmt_switch_time(end, now_b)} "
                f"之后再交给梁文谷。")

        if self._styled_off != off:
            self._apply_theme(off)
            self._styled_off = off

        self.bar.setValue(int(done * 1000))

        # --- 时间轴 / 值班表 / 接下来的交接 ---
        self.timeline.refresh()
        self.lbl_schedule.setText(f"今日值班：{day_schedule_text(now_b.date())}")
        ups = upcoming_switches(now_b, 3)
        parts = []
        for t, state in ups:
            name = "梁文谷" if state else "梁文峰"
            parts.append(f"{fmt_switch_time(t, now_b)} → {name}")
        self.lbl_next.setText("接下来：" + "　|　".join(parts))

        # --- 托盘 ---
        if self.tray is not None:
            self.tray.setToolTip(
                f"{APP_TITLE}\n现在：{'梁文谷（空闲 · 半价）' if off else '梁文峰（高峰 · 标准价）'}"
                f"\n距 {next_name}{next_verb}：{fmt_delta(remaining)}")
        self.setWindowTitle(
            f"{'🌙 梁文谷' if off else '⚡ 梁文峰'} · {fmt_delta(remaining)} · DeepSeek 峰谷时钟")

        self.lbl_notify_state.setText(
            "提醒已开启" if self.chk_notify.isChecked() else "提醒已关闭")

        # --- 状态变化 / 提前提醒 ---
        prev_off = self._off
        self._off = off
        if initial or prev_off is None:
            self._announce_current(off, remaining)
        elif prev_off != off:
            self._lead_fired = False
            self.notify(switch_to_off=off)
        else:
            self._maybe_lead_remind(off, remaining)

    # ------------------------- 主题 -------------------------

    def _apply_theme(self, off: bool):
        """按峰/空闲切换主视觉：Hero 渐变、名字配色、进度条、价格列高亮。"""
        if off:
            accent, soft = C_MINT, C_MINT_SOFT
            hero_qss = ("QFrame#Hero { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
                        " stop:0 #D8FBF1, stop:0.55 #E3F7FF, stop:1 #EFE9FF);"
                        " border: 1px solid #B9EFE1; border-radius: 22px; }")
            bar_qss = ("QProgressBar { border:none; border-radius:7px; background-color:#EAF6F4; }"
                       f"QProgressBar::chunk {{ border-radius:7px; background-color:{soft}; }}")
        else:
            accent, soft = C_PINK, C_PINK_SOFT
            hero_qss = ("QFrame#Hero { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
                        " stop:0 #FFE4ED, stop:0.55 #FFF1DE, stop:1 #FFF8EA);"
                        " border: 1px solid #FFD6E3; border-radius: 22px; }")
            bar_qss = ("QProgressBar { border:none; border-radius:7px; background-color:#FDF0F4; }"
                       f"QProgressBar::chunk {{ border-radius:7px; background-color:{soft}; }}")

        self._hero.setStyleSheet(hero_qss)
        self.bar.setStyleSheet(bar_qss)
        self.lbl_name.setStyleSheet(f"color:{accent}; background: transparent;")
        if self.tray is not None:
            self.tray.setIcon(self._icon_valley if off else self._icon_peak)

        mono = "font-family:'Cascadia Mono','Consolas',monospace; font-size:9.5pt;"
        idle = f"color:{C_TEXT_DIM}; background:transparent; {mono}"
        active = f"color:{accent}; background:transparent; font-weight:800; {mono}"
        for lab in getattr(self, "price_idle_labels", []):
            lab.setStyleSheet(active if off else idle)
        for lab in getattr(self, "price_peak_labels", []):
            lab.setStyleSheet(active if not off else idle)

    # ------------------------- 提醒 -------------------------

    def _announce_current(self, off: bool, remaining: timedelta):
        if off:
            self._set_banner(
                f"🌙 现在是【梁文谷】空闲时段，单价是高峰的一半，"
                f"还有 {human_delta(remaining)} 结束。")
        else:
            self._set_banner(
                f"⚡ 现在是【梁文峰】高峰时段，按标准价计费，"
                f"还有 {human_delta(remaining)} 进入空闲时段。")
        self._maybe_lead_remind(off, remaining)

    def _maybe_lead_remind(self, off: bool, remaining: timedelta):
        if off or self._lead_fired:
            return
        if not (self.chk_notify.isChecked() and self.chk_lead.isChecked()):
            return
        lead = self.spin_lead.value()
        if lead <= 0:
            return
        if remaining <= timedelta(minutes=lead):
            self._lead_fired = True
            self.notify(lead_minutes=lead)

    def notify(self, force: bool = False, test: bool = False,
               switch_to_off: bool | None = None, lead_minutes: int | None = None):
        """统一的提醒出口：托盘气泡 + 应用内横幅 + 可选提示音 + 任务栏闪烁。"""
        enabled = self.chk_notify.isChecked() or force

        if test:
            off = bool(self._off)
            name = "梁文谷" if off else "梁文峰"
            title = "🔔 通知测试"
            body = (f"如果你看到这条，说明提醒通道正常。"
                    f"现在值班的是【{name}】，"
                    f"{'空闲半价' if off else '高峰标准价'}。")
        elif lead_minutes is not None:
            title = f"⏰ 梁文谷 {lead_minutes} 分钟后上班"
            body = "空闲时段（半价）马上开始，长任务 / 批量任务可以先准备好，到点直接发车。"
        elif switch_to_off is True:
            title = "🌙 梁文谷已接班 · 空闲时段开始"
            body = "单价降到高峰的一半，跑批、长文本、深度推理现在最划算。"
        else:
            title = "⚡ 梁文峰已接班 · 高峰时段开始"
            body = "已回到高峰价。不急的活儿建议留到下一个空闲时段交给梁文谷。"

        self._set_banner(f"{title} —— {body}")

        if not enabled:
            return

        if self.tray is not None:
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 10000)
        if self.chk_sound.isChecked():
            QApplication.beep()
        if not self.isActiveWindow():
            QApplication.alert(self, 3000)

    def _set_banner(self, text: str):
        self.lbl_banner.setText(text)

    # ------------------------- 事件 -------------------------

    def closeEvent(self, ev):
        if self.chk_tray.isChecked() and self.tray is not None:
            ev.ignore()
            self._hide_to_tray()
        else:
            self._save_settings()
            ev.accept()
            # setQuitOnLastWindowClosed(False) 下要显式退出，否则会留下无窗口的进程
            QApplication.quit()

    def _quit(self):
        self._save_settings()
        if self._fetcher is not None and self._fetcher.isRunning():
            self._fetcher.wait(3000)
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()
