# -*- coding: utf-8 -*-
"""
DeepSeek 峰谷时钟 · DeepseekPeakClock
=====================================

一个浅色多巴胺风格的 PyQt5 桌面小工具，替你盯住 DeepSeek API 的
高峰 / 空闲（错峰）时段：

    高峰时段  ->  「梁文峰」值班（标准价）
    空闲时段  ->  「梁文谷」值班（价格为高峰的一半）

北京时间周一至周五（不含法定节假日）9:00-12:00、14:00-18:00 为高峰，
其余时间（含周末与法定节假日全天）都算空闲。规则不写死在代码里，
启动时后台联网获取 + 本地缓存 + 内置默认值三级兜底。

运行
----
    pip install -r requirements.txt
    python main.py

    python main.py --selftest   # 核心层 + 界面层自检，不弹窗
    python main.py --fetch      # 只测联网获取，打印原始结果
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import APP_NAME, APP_ORG, APP_VERSION     # noqa: E402


def _fix_stdio() -> None:
    """pythonw 启动时没有 stdout/stderr，print 会抛异常；这里兜一下。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _write_crash(text: str) -> None:
    try:
        from core.paths import app_path
        with open(app_path("crash.log"), "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n{text}\n")
    except Exception:
        pass


def _install_excepthooks() -> None:
    """
    PyQt5 遇到「槽函数里未捕获的异常」会直接调用 abort() 把进程干掉
    （退出码 0xC0000409）。界面用 pythonw 启动时没有控制台，看起来就是「闪退」。

    装上自定义 excepthook 后 PyQt5 不会再 abort：异常会写进 crash.log，
    同时打到 stderr，程序继续跑。
    """
    import threading
    import traceback

    def _hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        _write_crash(text)
        try:
            sys.stderr.write(text)
        except Exception:
            pass

    sys.excepthook = _hook
    threading.excepthook = lambda args: _hook(args.exc_type, args.exc_value,
                                              args.exc_traceback)


class _Tee:
    """把输出同时写往下游流和文件（打包成 --windowed 后没有控制台）。"""

    def __init__(self, stream, handle):
        self._stream = stream
        self._handle = handle

    def write(self, text):
        for target in (self._stream, self._handle):
            try:
                target.write(text)
            except Exception:
                pass
        self.flush()          # 随时落盘，中途挂掉也留得下已经跑完的部分
        return len(text)

    def flush(self):
        for target in (self._stream, self._handle):
            try:
                target.flush()
            except Exception:
                pass


def _run_selftest(argv: list) -> int:
    """跑两个自检脚本。--selftest-out=路径 可把结果同时写进文件。"""
    import runpy

    from core.paths import app_path, resource_path

    out_path = ""
    for arg in argv:
        if arg.startswith("--selftest-out="):
            out_path = arg.split("=", 1)[1].strip()

    handle = None
    if out_path:
        if not os.path.isabs(out_path):
            out_path = app_path(out_path)
        try:
            handle = open(out_path, "w", encoding="utf-8")
            sys.stdout = _Tee(sys.stdout, handle)
            sys.stderr = _Tee(sys.stderr, handle)
        except OSError as exc:
            print(f"自检结果无法写入 {out_path}：{exc}")

    rc = 0
    # runpy 会把 sys.modules["__main__"] 换成正在执行的脚本本身，
    # 所以先把入口模块存到一个固定名字下，自检脚本用这个名字取。
    entry = sys.modules.get("__main__")
    if entry is not None:
        sys.modules.setdefault("clock_entry", entry)

    for name in ("selftest_core.py", "selftest_ui.py"):
        path = ""
        for cand in (resource_path(name),
                     os.path.join(os.path.dirname(os.path.abspath(__file__)), name)):
            if os.path.exists(cand):
                path = cand
                break
        if not path:
            continue
        print(f"\n{'#' * 62}\n##########  {name}  ##########\n{'#' * 62}")
        try:
            runpy.run_path(path, run_name="__main__")
        except SystemExit as exc:
            rc = max(rc, int(exc.code or 0))

    print(f"\n>>> 自检结束，退出码 {rc}")
    if handle is not None:
        try:
            handle.flush()
            handle.close()
        except Exception:
            pass
    return rc


def do_fetch() -> int:
    """--fetch：立刻联网拉一次规则并写入缓存。"""
    from core.config import HTTP_TIMEOUT
    from core.feed import fetch_all
    from core.rules import apply_payload, cache_path, describe_rules, save_cache

    print(f"正在联网获取…（超时 {HTTP_TIMEOUT}s）")
    try:
        payload = fetch_all()
    except Exception as exc:
        print(f"失败：{type(exc).__name__}: {exc}")
        return 1
    apply_payload(payload)
    save_cache(payload)
    print("成功\n")
    describe_rules()
    print(f"\n缓存已写入：{cache_path()}")
    return 0


def main() -> int:
    _fix_stdio()
    _install_excepthooks()
    argv = sys.argv

    if "--fetch" in argv:
        return do_fetch()
    if "--selftest" in argv:
        return _run_selftest(argv)

    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QIcon
        from PyQt5.QtWidgets import QApplication
    except ImportError as exc:
        sys.stderr.write("没有找到 PyQt5，请先安装：\n    pip install PyQt5\n"
                         f"（原始错误：{exc}）\n")
        return 2

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Windows 任务栏图标需要显式设置 AppUserModelID，否则会归到 python.exe 上
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "DeepSeekTools.PeakClock")
        except Exception:
            pass

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    # 关掉窗口只是收进托盘，不该退出程序
    app.setQuitOnLastWindowClosed(False)

    from core.paths import icon_path
    ico = icon_path()
    if ico:
        app.setWindowIcon(QIcon(ico))

    from ui.window import PeakClockWindow
    win = PeakClockWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
