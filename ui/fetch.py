# -*- coding: utf-8 -*-
"""联网线程
========

把 `core.feed.fetch_all()` 放到后台线程里跑，别让界面卡住。
结果通过信号回主线程，Qt 的定时器和控件都只能在主线程碰。
"""

from __future__ import annotations
from PyQt5.QtCore import QThread, pyqtSignal
from core.config import HTTP_TIMEOUT
from core.feed import fetch_all


class RulesFetcher(QThread):
    """后台联网拉取规则/价格/节假日，避免卡住界面。"""

    rules_ready = pyqtSignal(dict)
    rules_failed = pyqtSignal(str)

    def __init__(self, parent=None, timeout: int = HTTP_TIMEOUT):
        super().__init__(parent)
        self.timeout = timeout

    def run(self):
        try:
            payload = fetch_all(self.timeout)
        except Exception as exc:
            self.rules_failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.rules_ready.emit(payload)
