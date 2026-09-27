# -*- coding: utf-8 -*-
"""
图标生成脚本
============

用 Qt 渲染应用图标并写出 `assets/app.ico`（多尺寸）与 `assets/app.png`。
ICO 容器直接手写：现代 ICO 允许内部直接放 PNG 数据，比引入额外的图像库可靠。

    python tools/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt           # noqa: E402
from PyQt5.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,  # noqa: E402
                         QPainterPath, QPen, QPixmap)
from PyQt5.QtWidgets import QApplication  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets")

# QApplication 的引用必须一直留着：一旦被回收，Qt 就认为没有 GUI 应用，
# 后面再建 QPixmap 会直接报 "Must construct a QGuiApplication before a QPixmap"。
_QAPP = None


def render(size: int, offpeak: bool = True) -> QPixmap:
    """
    画一个圆角渐变底 + 一条「峰谷曲线」的图标。

    空闲态用薄荷绿→天蓝，曲线落在谷底并画出「谷」字；
    高峰态用珊瑚粉→暖黄（应用图标统一用空闲态，这里保留参数给托盘用）。
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    s = float(size)

    g = QLinearGradient(0, 0, s, s)
    if offpeak:
        g.setColorAt(0.0, QColor("#63E3C6"))
        g.setColorAt(0.55, QColor("#7FD8F7"))
        g.setColorAt(1.0, QColor("#A78BFA"))
    else:
        g.setColorAt(0.0, QColor("#FF8FB1"))
        g.setColorAt(0.55, QColor("#FFA98A"))
        g.setColorAt(1.0, QColor("#FFC46B"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, s, s), s * 0.24, s * 0.24)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawPath(path)

    # 一条平滑的「峰 → 谷 → 峰」波形，正好对应高峰 / 空闲来回切换
    wave = QPainterPath()
    wave.moveTo(s * 0.14, s * 0.50)
    wave.cubicTo(s * 0.22, s * 0.16, s * 0.30, s * 0.16, s * 0.38, s * 0.46)
    wave.cubicTo(s * 0.46, s * 0.76, s * 0.54, s * 0.76, s * 0.62, s * 0.46)
    wave.cubicTo(s * 0.70, s * 0.16, s * 0.78, s * 0.16, s * 0.86, s * 0.50)
    pen = QPen(QColor(255, 255, 255, 240))
    pen.setWidthF(max(1.4, s * 0.085))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(wave)

    # 32px 以上才写字，再小就糊成一团了
    if size >= 32:
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(size * 0.185)
        f.setBold(True)
        f.setLetterSpacing(QFont.PercentageSpacing, 108)
        p.setFont(f)
        p.setPen(QPen(QColor(255, 255, 255, 235)))
        p.drawText(QRectF(0, s * 0.66, s, s * 0.28),
                   Qt.AlignHCenter | Qt.AlignTop, "峰谷")
    p.end()
    return pm


def png_bytes(pm: QPixmap) -> bytes:
    buf = QBuffer(QByteArray())
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return data


def write_ico(images: list[tuple[int, bytes]], path: str) -> None:
    """
    手写 ICO 容器。

    结构：ICONDIR(6 字节) + N × ICONDIRENTRY(16 字节) + 各尺寸图像数据。
    图像数据这里直接使用 PNG（Vista 之后的 ICO 都支持）。
    """
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(data), offset)
        blobs += data
        offset += len(data)
    with open(path, "wb") as fh:
        fh.write(header + entries + blobs)


def main() -> int:
    global _QAPP
    _QAPP = QApplication.instance() or QApplication(sys.argv)
    os.makedirs(OUT_DIR, exist_ok=True)

    images = []
    for size in SIZES:
        pm = render(size)
        images.append((size, png_bytes(pm)))
        if size == 256:
            pm.save(os.path.join(OUT_DIR, "app.png"), "PNG")

    ico_path = os.path.join(OUT_DIR, "app.ico")
    write_ico(images, ico_path)
    print(f"已生成 {ico_path}（{len(images)} 个尺寸：{SIZES}）")
    print(f"已生成 {os.path.join(OUT_DIR, 'app.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
