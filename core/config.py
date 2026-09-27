# -*- coding: utf-8 -*-
"""常量与默认值
============

峰谷规则、官方数据源地址、内置兜底规则与价格都集中在这里。
联网拿到的结果会覆盖 `ACTIVE`（见 `core.rules`），这里只是出厂默认值。
"""

from __future__ import annotations
from datetime import datetime, time as dtime, timedelta, timezone


APP_TITLE = "DeepSeek 峰谷时钟 · 梁文峰 / 梁文谷"
APP_ORG = "DeepSeekTools"
APP_NAME = "PeakValleyClock"

# ============================ 用户配置区 ============================

# 北京时间（DeepSeek 的峰谷时段按这个时区算）
TZ_BEIJING = timezone(timedelta(hours=8), "UTC+8")

# 数据源
PRICING_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
HOLIDAY_URLS = [
    "https://timor.tech/api/holiday/year/{year}",           # 主源
    "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json",  # 备用源
]
HTTP_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeepSeekPeakClock/2.0"

# 缓存文件（优先和脚本放一起，不可写则退回用户目录）
CACHE_NAME = ".deepseek_peak_clock_cache.json"

# 内置默认规则（联网失败且无缓存时使用）
# 来自官方定价页 2026-09：周一至周五 9:00-12:00、14:00-18:00 为高峰
DEFAULT_PEAK_WINDOWS = [(dtime(9, 0), dtime(12, 0)), (dtime(14, 0), dtime(18, 0))]
DEFAULT_PEAK_WORKDAY_ONLY = True
DEFAULT_WEEKEND_VALLEY = True

# 内置默认价格（元 / 百万 tokens，来自官方定价页 2026-09）
DEFAULT_MODELS = [
    {"name": "deepseek-flash",
     "idle": {"缓存命中输入": 0.02, "缓存未命中输入": 1.0, "输出": 4.0},
     "peak": {"缓存命中输入": 0.04, "缓存未命中输入": 2.0, "输出": 8.0}},
    {"name": "deepseek-v4-pro",
     "idle": {"缓存命中输入": 0.15, "缓存未命中输入": 4.5, "输出": 13.5},
     "peak": {"缓存命中输入": 0.30, "缓存未命中输入": 9.0, "输出": 27.0}},
]

# 内置默认节假日（离线兜底，只覆盖已公布的 2026 年；联网后会自动补全/更正）
DEFAULT_HOLIDAYS = [
    "2026-01-01", "2026-01-02", "2026-01-03",
    "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",
    "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23",
    "2026-04-04", "2026-04-05", "2026-04-06",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
    "2026-06-19", "2026-06-20", "2026-06-21",
    "2026-09-25", "2026-09-26", "2026-09-27",
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    "2026-10-05", "2026-10-06", "2026-10-07",
]

METRICS = ["缓存命中输入", "缓存未命中输入", "输出"]

def now_beijing() -> datetime:
    """当前北京时间（DeepSeek 的峰谷时段按这个时区算）。"""
    return datetime.now(TZ_BEIJING)
