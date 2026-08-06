# -*- coding: utf-8 -*-
"""市场数据层：① 龙虎榜  ② 同花顺题材热点  ③ 行业板块轮动  ④ 指数"""
import os
import json
import time
import requests
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import (UA, DATA_DIR, em_get, em_datacenter, tx_kline,
                    tx_symbol, prev_trade_day)

BOARD_CACHE = os.path.join(DATA_DIR, "boards_members.json")
# 东财行情主节点常对非住宅 IP 拒绝连接，push2delay 为可用备选
PUSH = "https://push2delay.eastmoney.com/api/qt/clist/get"
PUSH_HDR = {"Referer": "https://quote.eastmoney.com/center/boardlist.html"}


# ── ① 全市场龙虎榜 ────────────────────────────────────────
def fetch_lhb(date):
    rows, page = [], 1
    while True:
        part, pages = em_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=f"(TRADE_DATE>='{date}')(TRADE_DATE<='{date}')",
            page_size=100, page_number=page,
            sort_columns="BILLBOARD_NET_AMT", sort_types="-1")
        if not part:
            break
        rows.extend(part)
        if page >= pages:
            break
        page += 1

    recs = [{
        "code": r.get("SECURITY_CODE", ""),
        "name": r.get("SECURITY_NAME_ABBR", ""),
        "market": r.get("TRADE_MARKET", ""),
        "close": r.get("CLOSE_PRICE") or 0,
        "change_pct": round(float(r.get("CHANGE_RATE") or 0), 2),
        "turnover_pct": round(float(r.get("TURNOVERRATE") or 0), 2),
        "net_buy": float(r.get("BILLBOARD_NET_AMT") or 0),
        "buy_amt": float(r.get("BILLBOARD_BUY_AMT") or 0),
        "sell_amt": float(r.get("BILLBOARD_SELL_AMT") or 0),
        "deal_amt": float(r.get("BILLBOARD_DEAL_AMT") or 0),
        "accum_amount": float(r.get("ACCUM_AMOUNT") or 0),
        "deal_ratio": round(float(r.get("DEAL_AMOUNT_RATIO") or 0), 2),
        "free_mcap": float(r.get("FREE_MARKET_CAP") or 0),
        "reason": r.get("EXPLANATION", ""),
        "explain": r.get("EXPLAIN", ""),
    } for r in rows]

    # 同股多条上榜记录 → 取 |净买入| 最大者为主口径，原因合并
    g = defaultdict(list)
    for r in recs:
        g[r["code"]].append(r)
    merged = []
    for code, rs in g.items():
        main = max(rs, key=lambda x: abs(x["net_buy"]))
        reasons = []
        for x in sorted(rs, key=lambda x: -abs(x["net_buy"])):
            if x["reason"] not in reasons:
                reasons.append(x["reason"])
        m = dict(main)
        m.pop("reason", None)
        m["reasons"] = reasons
        m["n_rec"] = len(rs)
        merged.append(m)
    merged.sort(key=lambda x: -x["net_buy"])
    return merged, len(recs)


# ── ② 同花顺当日强势股 + 题材词频 ─────────────────────────
def fetch_hot(date):
    url = (f"http://zx.10jqka.com.cn/event/api/getharden/date/{date}"
           f"/orderby/date/orderway/desc/charset/GBK/")
    try:
        d = requests.get(url, headers={"User-Agent": UA}, timeout=15).json()
    except Exception:
        return [], []
    if d.get("errocode") != 0:
        return [], []
    hot = [{
        "code": x.get("code", ""), "name": x.get("name", ""),
        "reason": x.get("reason", "") or "",
        "close": x.get("close", 0),
        "change_pct": round(float(x.get("zhangfu") or 0), 2),
        "turnover_pct": round(float(x.get("huanshou") or 0), 2),
        "amount_wan": float(x.get("chengjiaoe") or 0),
    } for x in (d.get("data") or [])]
    hot.sort(key=lambda x: -x["change_pct"])

    cnt, tag_stocks = Counter(), defaultdict(list)
    for h in hot:
        for t in {t.strip() for t in h["reason"].split("+") if t.strip()}:
            cnt[t] += 1
            tag_stocks[t].append({"code": h["code"], "name": h["name"],
                                  "change_pct": h["change_pct"]})
    themes = [{"tag": t, "count": n,
               "stocks": sorted(tag_stocks[t], key=lambda s: -s["change_pct"])}
              for t, n in cnt.most_common()]
    return hot, themes


# ── ③ 行业板块成分股（缓存 7 天）──────────────────────────
def _push(params, tries=4):
    for i in range(tries):
        try:
            return em_get(PUSH, params=params, headers=PUSH_HDR, timeout=20,
                          tries=1).json()
        except Exception:
            time.sleep(1.2 * (i + 1))
    return None


def fetch_board_members(max_age_days=7, log=print):
    if os.path.exists(BOARD_CACHE):
        age = (time.time() - os.path.getmtime(BOARD_CACHE)) / 86400
        if age < max_age_days:
            log(f"  行业板块成分股缓存命中（{age:.1f} 天前）")
            return json.load(open(BOARD_CACHE, encoding="utf-8"))

    d = _push({"pn": "1", "pz": "200", "po": "1", "np": "1", "fltt": "2",
               "invt": "2", "fs": "m:90+t:2", "fields": "f12,f14"})
    boards = [{"code": x["f12"], "name": x["f14"]} for x in d["data"]["diff"]]
    out = {}
    for i, b in enumerate(boards, 1):
        members, pn = [], 1
        while True:
            dd = _push({"pn": str(pn), "pz": "200", "po": "1", "np": "1",
                        "fltt": "2", "invt": "2", "fs": f"b:{b['code']}",
                        "fields": "f12,f13,f14,f21"})
            diff = ((dd or {}).get("data") or {}).get("diff") or []
            if not diff:
                break
            total = dd["data"]["total"]
            members += [{"code": x.get("f12"), "name": x.get("f14"),
                         "mkt": x.get("f13"), "free_mcap": x.get("f21")}
                        for x in diff]
            if len(members) >= total or len(diff) < 200:
                break
            pn += 1
        out[b["code"]] = {"name": b["name"], "members": members}
        if i % 20 == 0:
            log(f"  板块成分股 {i}/{len(boards)}")
    json.dump(out, open(BOARD_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def fetch_quotes(codes_mkt, date, workers=20, log=print):
    """并发取个股在 date 的涨跌幅（腾讯前复权日K）"""
    from datetime import datetime, timedelta
    beg = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")

    def one(code, mkt):
        ks = tx_kline(tx_symbol(code, mkt), beg, date)
        if len(ks) < 2 or ks[-1][0] != date:
            return code, None
        prev, cur = float(ks[-2][2]), float(ks[-1][2])
        if prev <= 0:
            return code, None
        return code, {"close": cur, "prev": prev,
                      "chg": round((cur / prev - 1) * 100, 2)}

    res, done, t0 = {}, 0, time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, c, m) for c, m in codes_mkt.items()]
        for f in as_completed(futs):
            c, v = f.result()
            done += 1
            if v:
                res[c] = v
            if done % 800 == 0:
                log(f"  行情 {done}/{len(codes_mkt)}（{time.time()-t0:.0f}s）")
    log(f"  行情完成 {len(res)}/{len(codes_mkt)} 只（{time.time()-t0:.0f}s）")
    return res


def calc_boards(boards_raw, quotes):
    rows = []
    for bc, b in boards_raw.items():
        ms = [m for m in b["members"] if m["code"] in quotes]
        if not ms:
            continue
        up = sum(1 for m in ms if quotes[m["code"]]["chg"] > 0)
        dn = sum(1 for m in ms if quotes[m["code"]]["chg"] < 0)
        wsum = num = 0.0
        for m in ms:
            w = m.get("free_mcap")
            w = float(w) if isinstance(w, (int, float)) and w else 0.0
            wsum += w
            num += w * quotes[m["code"]]["chg"]
        wchg = (num / wsum) if wsum > 0 else sum(quotes[m["code"]]["chg"] for m in ms) / len(ms)
        eq = sum(quotes[m["code"]]["chg"] for m in ms) / len(ms)
        ld = max(ms, key=lambda m: quotes[m["code"]]["chg"])
        lg = min(ms, key=lambda m: quotes[m["code"]]["chg"])
        rows.append({
            "code": bc, "name": b["name"], "chg": round(wchg, 2),
            "chg_eq": round(eq, 2), "n": len(ms), "up": up, "down": dn,
            "flat": len(ms) - up - dn,
            "leader": {"code": ld["code"], "name": ld["name"], "chg": quotes[ld["code"]]["chg"]},
            "lagger": {"code": lg["code"], "name": lg["name"], "chg": quotes[lg["code"]]["chg"]},
            "free_mcap_yi": round(wsum / 1e8, 1)})
    rows.sort(key=lambda x: -x["chg"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


# ── ④ 指数 ───────────────────────────────────────────────
INDEXES = [("sh000001", "上证指数"), ("sz399001", "深证成指"),
           ("sz399006", "创业板指"), ("sh000688", "科创50"),
           ("sh000300", "沪深300"), ("sh000905", "中证500")]


def fetch_index(date):
    from datetime import datetime, timedelta
    beg = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")
    out = []
    for sym, nm in INDEXES:
        ks = tx_kline(sym, beg, date, fq="")
        if len(ks) >= 2 and ks[-1][0] == date:
            prev, cur = float(ks[-2][2]), float(ks[-1][2])
            out.append({"name": nm, "close": round(cur, 2),
                        "chg": round((cur / prev - 1) * 100, 2)})
    return out


# ── 汇总 ─────────────────────────────────────────────────
def build_market(date, log=print, stock_detail=True):
    if stock_detail:
        log("① 抓取全市场龙虎榜…")
        lhb, n_rec = fetch_lhb(date)
        log(f"   上榜 {len(lhb)} 只 / {n_rec} 条记录")

        log("② 抓取同花顺强势股题材…")
        hot, themes = fetch_hot(date)
        log(f"   强势股 {len(hot)} 只 / 题材标签 {len(themes)} 个")
    else:
        lhb, n_rec, hot, themes = [], 0, [], []
        log("①/② 跳过龙虎榜与同花顺强势股（基金版报告无需个股榜单）")

    # ③ 行业板块（容错：GitHub 等环境若被数据源限流，跳过但不影响其余）
    boards_raw, codes, quotes, boards = {}, {}, {}, []
    try:
        log("③ 抓取行业板块成分股…")
        boards_raw = fetch_board_members(log=log)
        codes = {m["code"]: m.get("mkt") for b in boards_raw.values() for m in b["members"]}
        log(f"   {len(boards_raw)} 个板块 / {len(codes)} 只成分股，取当日行情…")
        quotes = fetch_quotes(codes, date, log=log)
        boards = calc_boards(boards_raw, quotes)
    except Exception as e:
        log(f"   ! 行业板块抓取失败（跳过）：{e}")

    # ④ 指数（容错）
    index = []
    try:
        log("④ 抓取指数…")
        index = fetch_index(date)
    except Exception as e:
        log(f"   ! 指数抓取失败（跳过）：{e}")

    # 个股 → 所属行业映射
    stock2board = {}
    for bc, b in boards_raw.items():
        for m in b["members"]:
            stock2board.setdefault(m["code"], b["name"])

    mk = {"n": len(quotes),
          "up": sum(1 for v in quotes.values() if v["chg"] > 0),
          "down": sum(1 for v in quotes.values() if v["chg"] < 0)}
    mk["flat"] = mk["n"] - mk["up"] - mk["down"]
    mk["limit_up_like"] = sum(1 for v in quotes.values() if v["chg"] >= 9.8)
    mk["limit_down_like"] = sum(1 for v in quotes.values() if v["chg"] <= -9.8)

    hot_map = {h["code"]: h["reason"] for h in hot}
    for s in lhb:
        s["theme"] = hot_map.get(s["code"], "")

    reason_cnt = Counter()
    for s in lhb:
        for rs in s["reasons"]:
            reason_cnt[rs] += 1

    return {"date": date, "lhb": lhb, "lhb_records": n_rec, "hot": hot,
            "themes": themes, "boards": boards, "index": index,
            "market": mk, "quotes": quotes, "stock2board": stock2board,
            "reason_stat": reason_cnt.most_common(),
            "prev_date": prev_trade_day(date)}
