# -*- coding: utf-8 -*-
"""通用控件
========

托盘图标 + 卡片容器 + 24 小时时间轴。
时间轴横轴固定按北京时间画，本地时区和北京时间不一致时会多画一根游标。
"""

from __future__ import annotations
from datetime import datetime, time as dtime, timedelta
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap)
from PyQt5.QtWidgets import (QFrame, QSizePolicy, QWidget)
from theme import C_PURPLE, C_TEXT_DIM, C_YELLOW
from core.config import TZ_BEIJING, now_beijing
from core.engine import is_all_day_valley
from core.rules import ACTIVE, peak_windows


def make_icon(offpeak: bool, size: int = 64) -> QIcon:
    """生成托盘 / 通知图标：空闲是薄荷绿「谷」，高峰是珊瑚粉「峰」。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    g = QLinearGradient(0, 0, size, size)
    if offpeak:
        g.setColorAt(0.0, QColor("#63E3C6"))
        g.setColorAt(1.0, QColor("#6FC4FF"))
    else:
        g.setColorAt(0.0, QColor("#FF8FB1"))
        g.setColorAt(1.0, QColor("#FFC46B"))
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.30, size * 0.30)

    f = QFont("Microsoft YaHei UI")
    f.setPointSizeF(size * 0.44)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QPen(QColor("#FFFFFF")))
    p.drawText(QRectF(0, -size * 0.02, size, size), Qt.AlignCenter, "谷" if offpeak else "峰")
    p.end()
    return QIcon(pm)


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")


class DayTimeline(QWidget):
    """24 小时时间轴：高峰区间高亮 + 当前时刻游标。横轴为北京时间。"""

    PAD_X = 6
    BAR_H = 24
    BAR_TOP = 10
    LABEL_H = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.BAR_TOP + self.BAR_H + self.LABEL_H + 6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._peaks: list[tuple[datetime, datetime]] = []
        self._all_valley = False
        self._now_b = now_beijing()
        self._now_local = datetime.now().astimezone()
        self._today = self._now_b.date()
        self.refresh()

    def refresh(self) -> None:
        self._now_b = now_beijing()
        self._now_local = datetime.now().astimezone()
        self._today = self._now_b.date()
        day0 = datetime.combine(self._today, dtime(0, 0), TZ_BEIJING)
        day1 = day0 + timedelta(days=1)

        self._all_valley = is_all_day_valley(self._today)
        peaks: list[tuple[datetime, datetime]] = []
        if not self._all_valley and not (ACTIVE["peak_workday_only"]
                                         and self._today.weekday() >= 5):
            for s, e in peak_windows():
                ps = max(datetime.combine(self._today, s, TZ_BEIJING), day0)
                pe = min(datetime.combine(self._today, e, TZ_BEIJING), day1)
                if pe > ps:
                    peaks.append((ps, pe))
        self._peaks = peaks
        self.update()

    def _x(self, rect: QRectF, t: datetime) -> float:
        day0 = datetime.combine(self._today, dtime(0, 0), TZ_BEIJING)
        frac = (t - day0).total_seconds() / 86400.0
        return rect.left() + rect.width() * frac

    def paintEvent(self, _ev):
        w = self.width()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        bar = QRectF(self.PAD_X, self.BAR_TOP, max(10, w - 2 * self.PAD_X), self.BAR_H)
        radius = self.BAR_H / 2.0

        path = QPainterPath()
        path.addRoundedRect(bar, radius, radius)
        p.setClipPath(path)

        # 底：空闲色（一天里空闲占大多数）
        p.fillRect(bar, QColor("#9FEDDC"))
        # 高峰区间
        for s, e in self._peaks:
            x1, x2 = self._x(bar, s), self._x(bar, e)
            p.fillRect(QRectF(x1, bar.top(), max(1.0, x2 - x1), bar.height()),
                       QColor("#FFB3C7"))

        # 每小时分隔
        pen = QPen(QColor(255, 255, 255, 190))
        pen.setWidth(1)
        p.setPen(pen)
        for hh in range(1, 24):
            x = bar.left() + bar.width() * hh / 24.0
            p.drawLine(int(x), int(bar.top()), int(x), int(bar.bottom()))
        p.setClipping(False)

        # 边框
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#F0DFEC"), 1))
        p.drawRoundedRect(bar, radius, radius)

        # 小时刻度
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.setPen(QPen(QColor(C_TEXT_DIM)))
        for hh in range(0, 25, 3):
            x = bar.left() + bar.width() * hh / 24.0
            label = "24" if hh == 24 else f"{hh}"
            p.drawText(QRectF(x - 14, bar.bottom() + 2, 28, self.LABEL_H),
                       Qt.AlignHCenter | Qt.AlignTop, label)

        # 区间内文字
        f.setPointSizeF(8.0)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(QColor("#B0355F")))
        for s, e in self._peaks:
            x1, x2 = self._x(bar, s), self._x(bar, e)
            if x2 - x1 > 62:
                p.drawText(QRectF(x1, bar.top(), x2 - x1, bar.height()),
                           Qt.AlignCenter, "梁文峰 · 高峰")
        if self._all_valley:
            p.setPen(QPen(QColor("#0E8F79")))
            p.drawText(QRectF(bar.left(), bar.top(), bar.width(), bar.height()),
                       Qt.AlignCenter, "今天全天 梁文谷 · 空闲价")

        # 「现在」游标（北京时间）
        self._draw_marker(p, bar, self._now_b, QColor(C_PURPLE))

        # 本地游标（时区与北京时间不同时才画）
        if self._now_local.utcoffset() != timedelta(hours=8):
            local_as_bj = self._now_local.astimezone(TZ_BEIJING)
            if local_as_bj.date() == self._today:
                self._draw_marker(p, bar, local_as_bj, QColor(C_YELLOW))

        p.end()

    def _draw_marker(self, p: QPainter, bar: QRectF, t: datetime, color: QColor):
        if t.date() != self._today:
            return
        x = self._x(bar, t)
        p.setPen(QPen(color, 2))
        p.drawLine(int(x), int(bar.top() - 4), int(x), int(bar.bottom() + 4))
        p.setBrush(QBrush(color))
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.drawEllipse(QRectF(x - 4.5, bar.center().y() - 4.5, 9, 9))
