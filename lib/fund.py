# -*- coding: utf-8 -*-
"""基金层：持仓配置、净值、前十大重仓股、收益计算"""
import os
import re
import csv
import json
import html
import time
import requests
from datetime import datetime, timedelta

from common import UA, DATA_DIR, CONFIG_DIR, tx_kline, tx_symbol

HOLDINGS_CSV = os.path.join(CONFIG_DIR, "holdings.csv")
POS_CACHE = os.path.join(DATA_DIR, "fund_positions.json")

FS = requests.Session()
FS.headers.update({"User-Agent": UA, "Referer": "https://fund.eastmoney.com/"})

# 场内基金（ETF/LOF）代码前缀 → 走行情接口；其余按场外净值处理
ETF_PREFIX = ("51", "52", "56", "58", "159", "150", "161", "162", "163",
              "164", "165", "166", "167", "168", "50")


def is_exchange_fund(code):
    code = str(code).zfill(6)
    return code.startswith(ETF_PREFIX)


# ── 持仓配置 ─────────────────────────────────────────────
SAMPLE = [
    # code, name, shares, cost_nav, buy_date
    ("005827", "易方达蓝筹精选混合", 12000, 1.8520, "2026-03-12"),
    ("110022", "易方达消费行业股票", 8000, 3.4100, "2026-04-08"),
    ("161725", "招商中证白酒指数A", 15000, 0.9180, "2026-02-20"),
    ("510300", "华泰柏瑞沪深300ETF", 20000, 4.2600, "2026-01-15"),
    ("012414", "华夏中证半导体芯片ETF联接A", 10000, 1.2450, "2026-05-06"),
    ("003096", "中欧医疗健康混合A", 9000, 2.1300, "2026-04-22"),
]


def ensure_holdings(sample=True):
    """无持仓文件时生成模板（sample=True 填入示例持仓）"""
    if os.path.exists(HOLDINGS_CSV):
        return HOLDINGS_CSV
    with open(HOLDINGS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["基金代码", "基金名称(可留空自动获取)", "持有份额",
                    "成本单价", "买入日期(YYYY-MM-DD)"])
        if sample:
            for r in SAMPLE:
                w.writerow(r)
    return HOLDINGS_CSV


def load_holdings():
    if not os.path.exists(HOLDINGS_CSV):
        return []
    out = []
    with open(HOLDINGS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            vals = list(row.values())
            code = (vals[0] or "").strip()
            if not code or not code[0].isdigit():
                continue
            try:
                shares = float(str(vals[2]).replace(",", "") or 0)
                cost = float(str(vals[3]).replace(",", "") or 0)
            except ValueError:
                continue
            out.append({"code": code.zfill(6), "name": (vals[1] or "").strip(),
                        "shares": shares, "cost_nav": cost,
                        "buy_date": (vals[4] or "").strip()})
    return out


# ── 净值 ─────────────────────────────────────────────────
def fetch_nav_otc(code, date, back=20):
    """场外基金历史净值：返回 {date: {nav, acc_nav, chg}}"""
    try:
        r = FS.get("https://api.fund.eastmoney.com/f10/lsjz",
                   params={"fundCode": code, "pageIndex": 1, "pageSize": back},
                   timeout=15)
        lst = ((r.json().get("Data") or {}).get("LSJZList")) or []
    except Exception:
        return {}
    out = {}
    for x in lst:
        d = x.get("FSRQ")
        try:
            out[d] = {"nav": float(x.get("DWJZ") or 0),
                      "acc_nav": float(x.get("LJJZ") or 0),
                      "chg": float(x.get("JZZZL") or 0)}
        except (TypeError, ValueError):
            continue
    return out


def fetch_nav_etf(code, date):
    """场内基金：用二级市场收盘价（腾讯日K）"""
    beg = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y-%m-%d")
    ks = tx_kline(tx_symbol(code), beg, date)
    out = {}
    for i, k in enumerate(ks):
        nav = float(k[2])
        chg = 0.0
        if i > 0 and float(ks[i - 1][2]) > 0:
            chg = round((nav / float(ks[i - 1][2]) - 1) * 100, 2)
        out[k[0]] = {"nav": nav, "acc_nav": nav, "chg": chg}
    return out


def fetch_fund_name(code):
    try:
        r = FS.get("https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx",
                   params={"m": 1, "key": code}, timeout=12)
        for x in (r.json().get("Datas") or []):
            if x.get("CODE") == code:
                return x.get("NAME", "")
    except Exception:
        pass
    return ""


# ── 前十大重仓股（季报，带缓存）───────────────────────────
def fetch_positions(code, max_age_days=20):
    cache = {}
    if os.path.exists(POS_CACHE):
        try:
            cache = json.load(open(POS_CACHE, encoding="utf-8"))
        except Exception:
            cache = {}
    hit = cache.get(code)
    if hit and (time.time() - hit.get("_ts", 0)) / 86400 < max_age_days:
        return hit

    res = {"as_of": "", "stocks": [], "_ts": time.time()}
    try:
        r = FS.get("https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
                   params={"type": "jjcc", "code": code, "topline": 10,
                           "year": "", "month": "", "rt": "0.1"}, timeout=15)
        t = r.text
        m = re.search(r"截止至：<font class=.px12.>([\d-]+)</font>", t)
        res["as_of"] = m.group(1) if m else ""
        for row in re.findall(r"<tr>(?:(?!</tr>).)*?</tr>", t, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(tds) < 9:
                continue
            v = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in tds]
            if not v[0].isdigit():
                continue
            try:
                ratio = float(v[6].replace("%", "") or 0)
            except ValueError:
                ratio = 0.0
            res["stocks"].append({"code": v[1], "name": v[2], "ratio": ratio})
            if len(res["stocks"]) >= 10:
                break
    except Exception:
        pass

    cache[code] = res
    json.dump(cache, open(POS_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def stock_symbol(code):
    """重仓股代码 → 腾讯符号（区分 A股 / 港股）"""
    c = str(code).strip()
    if len(c) == 5 and c.isdigit():          # 港股 00700 / 09987
        return "hk" + c, "HK"
    if len(c) == 4 and c.isdigit():
        return "hk0" + c, "HK"
    if c.isdigit() and len(c) == 6:
        return tx_symbol(c), "A"
    return None, "OTHER"


def fetch_stock_chg(codes, date, workers=12):
    """重仓股当日涨跌幅（含港股）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    beg = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=16)).strftime("%Y-%m-%d")

    def one(c):
        sym, mtype = stock_symbol(c)
        if not sym:
            return c, None
        ks = tx_kline(sym, beg, date)
        if len(ks) < 2:
            return c, None
        # 港股与 A股 交易日可能不同，取 <=date 的最后一根
        ks = [k for k in ks if k[0] <= date]
        if len(ks) < 2:
            return c, None
        prev, cur = float(ks[-2][2]), float(ks[-1][2])
        if prev <= 0:
            return c, None
        return c, {"chg": round((cur / prev - 1) * 100, 2), "close": cur,
                   "mtype": mtype, "date": ks[-1][0]}

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(one, c) for c in set(codes)]):
            c, v = f.result()
            if v:
                out[c] = v
    return out


# ── 组合计算 ─────────────────────────────────────────────
def build_funds(date, log=print):
    hold = load_holdings()
    if not hold:
        return None
    log(f"  持仓 {len(hold)} 只基金，取净值与重仓股…")

    funds = []
    for h in hold:
        code = h["code"]
        etf = is_exchange_fund(code)
        # 支付宝等三方平台持有的均为「场外份额」，一律以官方单位净值为准；
        # 仅当净值接口无数据（如纯 ETF 未披露）时才回退到二级市场收盘价
        navs, src = fetch_nav_otc(code, date), "官方净值"
        if not navs:
            navs, src = fetch_nav_etf(code, date), "场内收盘价"
        # 取 <= date 的最新净值
        ds = sorted([d for d in navs if d <= date])
        if not ds:
            log(f"    ! {code} 无净值数据，跳过")
            continue
        cur_d = ds[-1]
        cur = navs[cur_d]
        nav = cur["nav"]
        chg = cur["chg"]
        name = h["name"] or fetch_fund_name(code) or code

        mv = nav * h["shares"]
        cost_mv = h["cost_nav"] * h["shares"]
        pnl = mv - cost_mv
        pnl_pct = (nav / h["cost_nav"] - 1) * 100 if h["cost_nav"] else 0
        day_pnl = mv * chg / (100 + chg) if chg != -100 else 0

        pos = fetch_positions(code)
        funds.append({
            "code": code, "name": name, "is_etf": etf,
            "shares": h["shares"], "cost_nav": h["cost_nav"],
            "buy_date": h["buy_date"], "nav": nav, "nav_date": cur_d,
            "nav_stale": cur_d != date,
            "chg": chg, "mv": mv, "cost_mv": cost_mv, "nav_src": src,
            "pnl": pnl, "pnl_pct": round(pnl_pct, 2), "day_pnl": day_pnl,
            "pos_as_of": pos.get("as_of", ""),
            "positions": pos.get("stocks", []),
        })
        log(f"    {code} {name[:16]:<16} 净值{nav:.4f}({cur_d},{src}) {chg:+.2f}% "
            f"重仓股{len(pos.get('stocks', []))}只")

    if not funds:
        return None

    # 重仓股当日行情
    allc = [s["code"] for f in funds for s in f["positions"]]
    log(f"  取 {len(set(allc))} 只重仓股当日行情…")
    chgs = fetch_stock_chg(allc, date)
    for f in funds:
        for s in f["positions"]:
            q = chgs.get(s["code"])
            s["chg"] = q["chg"] if q else None
            s["mtype"] = q["mtype"] if q else "?"
            s["contrib"] = (q["chg"] * s["ratio"] / 100) if q else None

    tot_mv = sum(f["mv"] for f in funds)
    tot_cost = sum(f["cost_mv"] for f in funds)
    tot_day = sum(f["day_pnl"] for f in funds)
    port = {
        "n": len(funds), "mv": tot_mv, "cost": tot_cost,
        "pnl": tot_mv - tot_cost,
        "pnl_pct": round((tot_mv / tot_cost - 1) * 100, 2) if tot_cost else 0,
        "day_pnl": tot_day,
        "day_pct": round(tot_day / (tot_mv - tot_day) * 100, 2) if (tot_mv - tot_day) else 0,
        "win": sum(1 for f in funds if f["pnl"] > 0),
        "lose": sum(1 for f in funds if f["pnl"] < 0),
        "day_up": sum(1 for f in funds if f["chg"] > 0),
        "day_down": sum(1 for f in funds if f["chg"] < 0),
        "stale": sum(1 for f in funds if f["nav_stale"]),
    }
    for f in funds:
        f["weight"] = round(f["mv"] / tot_mv * 100, 2) if tot_mv else 0
    funds.sort(key=lambda x: -x["mv"])
    return {"funds": funds, "portfolio": port, "stock_chg": chgs}
