# -*- coding: utf-8 -*-
"""基金全量数据层：从天天基金排行榜取全部开放式基金的多维业绩，
本地排序生成「基金排行榜」数据集，并导出可内嵌 HTML 的紧凑 FUND_DB
（用于离线交互式查询：输入基金代码 → 展示净值/业绩/榜单归属）。

数据源：fund.eastmoney.com/data/rankhandler.aspx
字段(按 "," 拆分后索引)：
  0 代码 1 名称 2 拼音 3 净值日期 4 单位净值 5 累计净值
  6 日增长率 7 近1周 8 近1月 9 近3月 10 近6月 11 近1年
  12 近2年 13 近3年 14 今年来 15 成立来 16 成立日期
"""
import os
import re
import json
import time
import statistics
import requests

from common import DATA_DIR

CACHE = os.path.join(DATA_DIR, "fund_universe.json")
RANK_URL = "https://fund.eastmoney.com/data/rankhandler.aspx"
HDR = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"),
       "Referer": "https://fund.eastmoney.com/"}

# 基金类型枚举（与 rankhandler 的 ft 参数一一对应）
TYPES = [("gp", "股票型"), ("hh", "混合型"), ("zs", "指数型"),
         ("zq", "债券型"), ("qdii", "QDII"), ("fof", "FOF")]

S = requests.Session()
S.headers.update(HDR)
_last = [0.0]
_GAP = 1.2


def _get(ft):
    global _last
    w = _GAP - (time.time() - _last[0])
    if w > 0:
        time.sleep(w + 0.1)
    u = (f"{RANK_URL}?op=ph&dt=kf&ft={ft}&rs=&gs=0&sc=rzdf&st=desc"
         f"&pi=1&pn=10000&dx=1&_={int(time.time()*1000)}")
    r = S.get(u, timeout=30)
    _last[0] = time.time()
    return r.text


# 规范列序（所有记录统一）：
# 0 代码 1 名称 2 类型 3 单位净值 4 净值日期(int) 5 日涨跌% 6 近1周% 7 近1月% 8 近1年%
DAY, W1, M1, Y1 = 5, 6, 7, 8


def _parse(text, ft):
    """把 rankhandler 文本解析为规范 9 字段记录列表"""
    m = re.search(r"var rankData\s*=\s*\{datas:\[(.*?)\],allRecords", text, re.S)
    if not m:
        return []
    out = []
    for row in m.group(1).split('","'):
        row = row.strip().strip('"')
        p = row.split(",")
        if len(p) < 12 or not p[0].isdigit():
            continue
        def f(i):
            v = p[i] if i < len(p) else ""
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        navdate = p[3].replace("-", "") if len(p) > 3 and p[3] else ""
        try:
            navdate = int(navdate) if navdate else 0
        except ValueError:
            navdate = 0
        out.append([p[0], p[1], ft, f(4), navdate,
                    f(6), f(7), f(8), f(11)])
    return out


def build_universe(date, max_age_days=1, log=print):
    """取全市场基金快照，返回可内嵌的 FUND_DB 字典

    记录格式(每条 9 字段)：[代码, 名称, 单位净值, 净值日期(int YYYYMMDD),
    日涨跌%, 近1周%, 近1月%, 近1年%]
    """
    # 命中缓存
    if os.path.exists(CACHE):
        try:
            c = json.load(open(CACHE, encoding="utf-8"))
            age = (time.time() - c.get("_ts", 0)) / 86400
            if c.get("db", {}).get("date") == date and age < max_age_days:
                log(f"  基金全量数据缓存命中（{age:.1f} 天前，{len(c['db']['all'])} 只）")
                return c["db"]
        except Exception:
            pass

    log("  抓取天天基金全量排行榜（按类型分页）…")
    by_type = {}
    for ft, label in TYPES:
        recs = _parse(_get(ft), ft)
        by_type[ft] = recs
        log(f"    {label}({ft}) {len(recs)} 只")

    # 合并全部（去重：同一代码保留首次出现的类型）
    allrec = []
    seen = set()
    for ft, _ in TYPES:
        for r in by_type[ft]:
            code = r[0]
            if code in seen:
                continue
            seen.add(code)
            allrec.append(r)

    # ── 赚钱效应概览 ──
    days = [r[DAY] for r in allrec if r[DAY] is not None]
    up = sum(1 for d in days if d > 0)
    dn = sum(1 for d in days if d < 0)
    fl = len(days) - up - dn
    avg = round(statistics.fmean(days), 3) if days else 0
    med = round(statistics.median(days), 3) if days else 0
    best = max(allrec, key=lambda r: r[DAY] if r[DAY] is not None else -1e9)
    worst = min(allrec, key=lambda r: r[DAY] if r[DAY] is not None else 1e9)
    summary = {"n": len(allrec), "up": up, "down": dn, "flat": fl,
               "avg": avg, "median": med,
               "up_ratio": round(up / len(days) * 100, 1) if days else 0,
               "best": [best[0], best[1], best[DAY]],
               "worst": [worst[0], worst[1], worst[DAY]]}

    # ── 各类型分布 ──
    type_dist = []
    for ft, label in TYPES:
        rs = by_type[ft]
        td = [r[DAY] for r in rs if r[DAY] is not None]
        type_dist.append([ft, label, len(rs),
                          round(statistics.fmean(td), 3) if td else 0,
                          sum(1 for x in td if x > 0)])

    # ── 排行榜（各维度 × 各类型，取 TOP80）──
    dims = {"day": DAY, "w1": W1, "m1": M1, "y1": Y1}

    def topn(recs, idx, n=80):
        valid = [r for r in recs if r[idx] is not None]
        valid.sort(key=lambda r: -r[idx])
        return [r[0] for r in valid[:n]]

    rank = {}
    for dim, idx in dims.items():
        rank[dim] = {"all": topn(allrec, idx)}
        for ft, _ in TYPES:
            rank[dim][ft] = topn(by_type[ft], idx)

    db = {"date": date, "types": {ft: lb for ft, lb in TYPES},
          "summary": summary, "type_dist": type_dist,
          "all": allrec, "rank": rank}
    json.dump({"_ts": time.time(), "db": db},
              open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"  基金全量 {len(allrec)} 只，已缓存（{os.path.getsize(CACHE)//1024} KB）")
    return db


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "2026-08-05"
    db = build_universe(d)
    print("总数:", db["summary"])
    import json as _j
    print("嵌入 JSON 体积 ≈", len(_j.dumps(db, ensure_ascii=False)) // 1024, "KB")
