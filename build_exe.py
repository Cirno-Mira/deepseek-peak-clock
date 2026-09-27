# -*- coding: utf-8 -*-
"""
打包成单文件 exe
================

用法：

    python build_exe.py                   # 发布：单文件、无控制台
    python build_exe.py --debug           # 排查：单文件 + 控制台 + bootloader 日志
    python build_exe.py --debug --onedir  # 排查：单目录版本

产物：`dist/DeepseekPeakClock.exe`，单文件、免安装、带图标。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "DeepseekPeakClock"
ICON = os.path.join(HERE, "assets", "app.ico")

# 运行时才 import、PyInstaller 静态分析看不到的模块
HIDDEN = [
    "PyQt5.sip",
]

# 附带资源：源目录;包内目录（Windows 用分号）
# 自检脚本一起打进去，这样 exe 也能跑 --selftest（打包后没控制台，见 --selftest-out）
DATAS = [
    ("assets", "assets"),
    ("selftest_core.py", "."),
    ("selftest_ui.py", "."),
]

# conda 把 OpenSSL / zlib / ffi 这些运行库放在 Library\bin，而不是解释器根目录，
# PyInstaller 顺着 pyd 找不到它们（会打印 "Library not found"）。
# 这个程序要用 https 拉定价页和节假日，缺了 ssl 就直接连不上，所以显式带上。
CONDA_DLLS = [
    "libssl-3-x64.dll",
    "libcrypto-3-x64.dll",
    "liblzma.dll",
    "libbz2.dll",
    "ffi.dll",
    "sqlite3.dll",
    "zlib1.dll",
    "libz.dll",
    "libexpat.dll",
    "libiconv-2.dll",
]


def _conda_bin() -> str:
    """conda 环境下 Library\\bin 的位置（非 conda 环境返回空串）。"""
    cand = os.path.join(sys.prefix, "Library", "bin")
    return cand if os.path.isdir(cand) else ""


def build(debug: bool = False, onefile: bool = True) -> int:
    """
    debug=True 时改成「控制台 + bootloader 调试输出」，用来排查打包后启动即退出的问题。
    """
    try:
        __import__("PyInstaller")
    except ImportError:
        print("缺少 PyInstaller，先执行：pip install pyinstaller -i "
              "https://mirrors.aliyun.com/pypi/simple/")
        return 1

    if not os.path.exists(ICON):
        print("找不到 assets/app.ico，先执行：python tools/make_icon.py")
        return 1

    name = f"{APP_NAME}Debug" if debug else APP_NAME
    out_dir = os.path.join(HERE, "dist_debug" if debug else "dist")

    # 每次都从干净状态开始，避免上次的缓存混进来
    for d in ("build", out_dir):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    for f in (f"{APP_NAME}.spec", f"{APP_NAME}Debug.spec"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile" if onefile else "--onedir",
        "--windowed" if not debug else "--console",
        "--name", name,
        "--icon", ICON,
        "--distpath", out_dir,
        "--workpath", os.path.join(HERE, "build"),
        "--specpath", HERE,
    ]
    if debug:
        cmd += ["--debug", "bootloader", "--log-level", "DEBUG"]

    for src, dst in DATAS:
        cmd += ["--add-data", f"{os.path.join(HERE, src)}{os.pathsep}{dst}"]

    bin_dir = _conda_bin()
    if bin_dir:
        for dll in CONDA_DLLS:
            src = os.path.join(bin_dir, dll)
            if os.path.exists(src):
                cmd += ["--add-binary", f"{src}{os.pathsep}."]

    for mod in HIDDEN:
        cmd += ["--hidden-import", mod]
    cmd += [
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        os.path.join(HERE, "main.py"),
    ]

    print("执行：\n  " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n")
    rc = subprocess.call(cmd, cwd=HERE)
    if rc != 0:
        print(f"\n打包失败，PyInstaller 退出码 {rc}")
        return rc

    exe = ""
    for _ in range(20):                      # 杀软/索引器可能短暂占着刚写出来的文件
        for cand in (os.path.join(out_dir, f"{name}.exe"),
                     os.path.join(out_dir, name, f"{name}.exe")):   # 后者是单目录模式
            if os.path.isfile(cand):
                exe = cand
                break
        if exe:
            break
        time.sleep(0.25)

    if exe:
        size = os.path.getsize(exe) / 1024 / 1024
        print(f"\n完成：{exe}   （{size:.1f} MB）")
        return 0

    print(f"\nPyInstaller 正常结束，但 {out_dir} 下没找到 {name}.exe。")
    try:
        for entry in sorted(os.listdir(out_dir)):
            print("   ", entry)
    except OSError as exc:
        print(f"    （连目录都读不了：{exc}）")
    return 1


if __name__ == "__main__":
    _debug = "--debug" in sys.argv
    _onefile = "--onedir" not in sys.argv
    sys.exit(build(debug=_debug, onefile=_onefile))
