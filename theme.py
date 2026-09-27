# -*- coding: utf-8 -*-
"""配色与样式表
============

浅色多巴胺配色：空闲用薄荷绿，高峰用珊瑚粉，其余是紫白底。
只放颜色常量和 QSS，不依赖任何项目内模块。
"""

from __future__ import annotations


C_TEXT = "#4B3F6B"
C_TEXT_DIM = "#8C81AB"
C_PURPLE = "#7C5CFF"
C_MINT = "#12B99C"
C_MINT_SOFT = "#8FE9D7"
C_PINK = "#F0508A"
C_PINK_SOFT = "#FFB3C7"
C_YELLOW = "#FFC46B"
C_WARN = "#D98A2B"
C_OK = "#12B99C"

QSS = """
QWidget#Root {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0.00 #FFF2F8,
                                stop:0.33 #FFFAED,
                                stop:0.66 #EAF7FF,
                                stop:1.00 #F4EEFF);
}
QLabel {
    color: #4B3F6B;
    font-family: 'Microsoft YaHei UI', 'Segoe UI', 'Segoe UI Emoji', sans-serif;
    background: transparent;
}
QLabel#H1      { font-size: 19pt; font-weight: 800; color: #3A2E5C; }
QLabel#Sub     { font-size: 9.5pt; color: #8C81AB; }
QLabel#CardT   { font-size: 11pt; font-weight: 700; color: #6B5CA5; }
QLabel#Dim     { font-size: 9.5pt; color: #8C81AB; }
QLabel#Clock   { font-size: 40pt; font-weight: 800; color: #2F2750; }
QLabel#HeroName{ font-size: 34pt; font-weight: 800; }
QLabel#Countdown {
    font-family: 'Cascadia Mono', 'Consolas', 'Microsoft YaHei UI', monospace;
    font-size: 20pt; font-weight: 800; color: #3A2E5C;
}
QLabel#Date    { font-size: 11pt; color: #6B5CA5; }
QLabel#Mono    { font-family: 'Cascadia Mono', 'Consolas', 'Microsoft YaHei UI', monospace; }
QLabel#Banner  {
    background-color: #FFF8E8; border: 1px solid #FFE4BC; border-radius: 12px;
    padding: 8px 12px; color: #8A6A2F; font-size: 9.5pt;
}
QLabel#Tag {
    background-color: #F3EEFF; border-radius: 10px; padding: 3px 10px;
    color: #7C5CFF; font-size: 9pt; font-weight: 700;
}
QFrame#Card {
    background-color: rgba(255, 255, 255, 0.88);
    border: 1px solid #EFE6FF;
    border-radius: 20px;
}
QFrame#Hero { border-radius: 22px; }
QFrame#Line { background-color: #F0E9FF; border: none; max-height: 1px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: #E3D9F7; border-radius: 5px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: #CDBBF2; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QPushButton#Pill {
    background-color: #FFFFFF; border: 1px solid #E7DCFA; border-radius: 14px;
    padding: 6px 14px; color: #6B5CA5; font-size: 9.5pt; font-weight: 700;
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
}
QPushButton#Pill:hover   { background-color: #F7F2FF; border-color: #CDB8F7; }
QPushButton#Pill:pressed { background-color: #EFE6FF; }
QPushButton#Pill:disabled { color: #BDB3D4; background-color: #F7F5FB; }
QPushButton#Pill:checked { background-color: #A78BFA; border-color: #A78BFA; color: #FFFFFF; }
QCheckBox {
    color: #5A4E7C; font-size: 10pt; spacing: 8px;
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
}
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 5px;
    border: 1.5px solid #D9CDF5; background: #FFFFFF;
}
QCheckBox::indicator:hover   { border-color: #B9A3F0; }
QCheckBox::indicator:checked { background: #A78BFA; border-color: #A78BFA; }
QSpinBox {
    border: 1px solid #E5DBFA; border-radius: 10px; padding: 3px 8px;
    background: #FFFFFF; color: #5A4E7C; font-size: 10pt; min-width: 56px;
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
}
QProgressBar { border: none; border-radius: 7px; background-color: #F1ECFA; }
QProgressBar::chunk { border-radius: 7px; }
QToolTip {
    background-color: #FFFFFF; color: #5A4E7C; border: 1px solid #E7DCFA;
    border-radius: 8px; padding: 6px 10px;
}
"""
