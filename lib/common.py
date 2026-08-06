# -*- coding: utf-8 -*-
"""公共工具：HTTP 会话、东财节流、交易日判断"""
import os
import time
import random
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
REPORT_DIR = os.path.join(ROOT, "reports")
CONFIG_DIR = os.path.join(ROOT, "config")
for _d in (DATA_DIR, REPORT_DIR, CONFIG_DIR):
    os.makedirs(_d, exist_ok=True)

# ── 东财：统一节流入口（串行 + 抖动，防封 IP）──────────────
EM = requests.Session()
EM.headers.update({"User-Agent": UA, "Accept": "*/*",
                   "Accept-Language": "zh-CN,zh;q=0.9"})
_EM_GAP = 1.0
_em_last = [0.0]


def em_get(url, params=None, headers=None, timeout=20, tries=4, **kw):
    for i in range(tries):
        w = _EM_GAP - (time.time() - _em_last[0])
        if w > 0:
            time.sleep(w + random.uniform(0.05, 0.35))
        try:
            r = EM.get(url, params=params, headers=headers, timeout=timeout, **kw)
            _em_last[0] = time.time()
            return r
        except Exception:
            _em_last[0] = time.time()
            if i == tries - 1:
                raise
            time.sleep(1.2 * (i + 1))


def em_datacenter(report_name, columns="ALL", filter_str="", page_size=100,
                  page_number=1, sort_columns="", sort_types="-1"):
    """东财数据中心报表通用接口"""
    r = em_get("https://datacenter-web.eastmoney.com/api/data/v1/get", params={
        "reportName": report_name, "columns": columns, "filter": filter_str,
        "pageNumber": str(page_number), "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB"})
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"], d["result"].get("pages", 1)
    return [], 0


# ── 腾讯行情（不封 IP，用于历史日K）───────────────────────
TX = requests.Session()
TX.headers.update({"User-Agent": UA})
TX_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def tx_symbol(code, mkt=None):
    """A股代码 → 腾讯符号"""
    code = str(code).zfill(6)
    if mkt == 1:
        return "sh" + code
    if mkt == 0:
        return "sz" + code
    if code.startswith(("6", "9", "5")):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def tx_kline(symbol, beg, end, fq="qfq", tries=3, timeout=12):
    """取前复权日K：[[日期,开,收,高,低,量], ...]"""
    url = f"{TX_KLINE}?param={symbol},day,{beg},{end},20,{fq}"
    for _ in range(tries):
        try:
            d = TX.get(url, timeout=timeout).json()
            node = (d.get("data") or {}).get(symbol) or {}
            return node.get("qfqday") or node.get("day") or []
        except Exception:
            time.sleep(0.6)
    return []


# ── 交易日 ────────────────────────────────────────────────
def recent_trade_days(end_date, n=12):
    """以上证指数为基准，返回 <=end_date 的最近 n 个交易日（升序）"""
    from datetime import datetime, timedelta
    e = datetime.strptime(end_date, "%Y-%m-%d")
    beg = (e - timedelta(days=n * 3 + 20)).strftime("%Y-%m-%d")
    ks = tx_kline("sh000001", beg, end_date, fq="")
    return [k[0] for k in ks if k[0] <= end_date][-n:]


def is_trade_day(date):
    days = recent_trade_days(date, 6)
    return bool(days) and days[-1] == date


def resolve_date(arg=None, today=None):
    """解析目标交易日：
       - 指定日期 → 校验是否交易日
       - 未指定  → 取最近交易日（当天若为交易日但未收盘，回退到上一交易日）
    """
    from datetime import datetime
    now = datetime.now()
    today = today or now.strftime("%Y-%m-%d")
    if arg:
        days = recent_trade_days(arg, 6)
        return (arg, bool(days) and days[-1] == arg)
    days = recent_trade_days(today, 8)
    if not days:
        return today, False
    last = days[-1]
    # 当日为交易日但尚未收盘（15:05 前）→ 用上一交易日
    if last == today and now.hour * 60 + now.minute < 15 * 60 + 5:
        last = days[-2] if len(days) > 1 else last
    return last, True


def prev_trade_day(date):
    days = recent_trade_days(date, 6)
    if date in days:
        i = days.index(date)
        return days[i - 1] if i > 0 else None
    return days[-1] if days else None
