# -*- coding: utf-8 -*-
"""联网获取层
==========

从官方定价页解析高峰时段与模型价格，从公开接口取中国法定节假日。
所有函数只做「取回来 + 解析」，失败就抛异常，由上层决定退回缓存还是内置默认。
"""

from __future__ import annotations
import json
import re
import urllib.request
from datetime import time as dtime
from core.config import (HOLIDAY_URLS, HTTP_TIMEOUT, PRICING_URL,
                         USER_AGENT)
from core.config import now_beijing


def _http_get(url: str, timeout: int = HTTP_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "identity",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_text(url: str, timeout: int = HTTP_TIMEOUT) -> str:
    raw = _http_get(url, timeout)
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _strip_html(html: str) -> str:
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&mdash;", "-"), ("&ndash;", "-")):
        t = t.replace(a, b)
    return t


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def parse_pricing_page(html: str) -> dict:
    """
    从官方定价页解析出：高峰时段、是否只限工作日、模型价格表。
    解析不出来就抛异常，由上层退回缓存/内置默认。
    """
    flat = _squash(_strip_html(html))

    # --- 1. 高峰时段 ---
    note = ""
    m = (re.search(r"北京时间(.{0,90}?)为高峰时段", flat)
         or re.search(r"高峰时段为北京时间(.{0,90}?)[。（(]", flat))
    windows: list[tuple[dtime, dtime]] = []
    if m:
        note = m.group(1)
        for a, b, c, d in re.findall(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", note):
            windows.append((dtime(int(a), int(b)), dtime(int(c), int(d))))
    if not windows:
        raise ValueError("定价页里没找到「高峰时段」时间，页面结构可能变了")

    # --- 2. 周末 / 节假日是否整天算空闲 ---
    weekend_valley = "周末" in flat
    workday_only = "周一至周五" in flat or "周一至周五" in note

    # --- 3. 模型名与价格 ---
    mm = re.search(r"模型(.*?)BASEURL", flat)
    names = []
    if mm:
        names = [n for n in re.findall(r"deepseek-[a-z0-9.\-]+", mm.group(1))]
    if not names:
        raise ValueError("定价页里没找到模型名")

    token_of = {
        "缓存命中输入": "百万tokens输入（缓存命中）",
        "缓存未命中输入": "百万tokens输入（缓存未命中）",
        "输出": "百万tokens输出",
    }
    models = {n: {"name": n, "idle": {}, "peak": {}} for n in names}
    for label, token in token_of.items():
        r = re.search(re.escape(token)
                      + r"空闲时段((?:\d+(?:\.\d+)?元)+)"
                        r"高峰时段((?:\d+(?:\.\d+)?元)+)", flat)
        if not r:
            continue
        idle = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)元", r.group(1))]
        peak = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)元", r.group(2))]
        for i, n in enumerate(names):
            if i < len(idle):
                models[n]["idle"][label] = idle[i]
            if i < len(peak):
                models[n]["peak"][label] = peak[i]

    out = [models[n] for n in names if models[n]["peak"]]
    if not out:
        raise ValueError("定价页里没解析出价格表")

    return {
        "peak_windows": windows,
        "peak_workday_only": workday_only,
        "weekend_valley": weekend_valley,
        "models": out,
        "note": note,
    }


def fetch_holidays(year: int, timeout: int = HTTP_TIMEOUT) -> set[str]:
    """从若干公开数据源取某年的中国法定节假日（放假日）日期集合，ISO 字符串。"""
    errors = []
    for tpl in HOLIDAY_URLS:
        url = tpl.format(year=year)
        try:
            if "timor.tech" in url:
                data = json.loads(_http_get_text(url, timeout))
                if data.get("code") != 0:
                    raise ValueError(f"timor 返回 code={data.get('code')}")
                days = {v["date"] for v in data["holiday"].values()
                        if v.get("holiday") is True and v.get("date")}
            else:
                data = json.loads(_http_get_text(url, timeout))
                days = {d["date"] for d in data.get("days", [])
                        if d.get("isOffDay") is True and d.get("date")}
            if days:
                return days
            errors.append(f"{url}: 空数据")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__} {exc}")
    raise RuntimeError("; ".join(errors[:2]))


def fetch_all(timeout: int = HTTP_TIMEOUT) -> dict:
    """联网获取规则 + 价格 + 节假日，返回可直接落盘/生效的 payload。"""
    parsed = parse_pricing_page(_http_get_text(PRICING_URL, timeout))

    this_year = now_beijing().year
    holidays: set[str] = set()
    good_years: list[int] = []
    holiday_error = ""
    for y in (this_year, this_year + 1):
        try:
            got = fetch_holidays(y, timeout)
        except Exception as exc:
            # 明年的放假安排通常还没公布，取不到不算错误，静默跳过
            if y == this_year:
                holiday_error = str(exc)
            continue
        holidays |= got
        good_years.append(y)

    parsed.update({
        "holidays": sorted(holidays),
        "holiday_years": good_years,
        "holiday_error": holiday_error,
        "origin": "live",
        "source": PRICING_URL,
        "fetched_at": now_beijing().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return parsed
