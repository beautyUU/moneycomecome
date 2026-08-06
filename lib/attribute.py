# -*- coding: utf-8 -*-
"""归因引擎：把「我的基金」与「当日市场情绪」打通

核心链路：
  基金 → 前十大重仓股 → 当日涨跌 × 占净值比例 → 涨跌贡献
                      → 是否上龙虎榜 / 是否为强势股 / 所属行业板块表现
                      → 重仓股题材标签聚合 → 组合题材暴露
"""
from collections import defaultdict


def attribute(fund_data, market):
    """在 fund_data 上原地补充归因字段，并返回组合级归因摘要"""
    funds = fund_data["funds"]
    lhb_map = {s["code"]: s for s in market["lhb"]}
    hot_map = {h["code"]: h for h in market["hot"]}
    board_map = {b["name"]: b for b in market["boards"]}
    s2b = market["stock2board"]

    # ── 个基归因 ──────────────────────────────────────────
    for f in funds:
        cov_ratio = 0.0      # 已覆盖(取到行情)的重仓股占净值合计
        contrib_sum = 0.0
        for s in f["positions"]:
            code = s["code"]
            s["board"] = s2b.get(code, "")
            b = board_map.get(s["board"])
            s["board_chg"] = b["chg"] if b else None
            lh = lhb_map.get(code)
            s["on_lhb"] = bool(lh)
            s["lhb_net"] = lh["net_buy"] if lh else None
            s["lhb_reason"] = lh["reasons"][0] if lh else ""
            ht = hot_map.get(code)
            s["is_hot"] = bool(ht)
            s["theme"] = ht["reason"] if ht else ""
            if s.get("chg") is not None:
                cov_ratio += s["ratio"]
                contrib_sum += s["contrib"]
        f["pos_coverage"] = round(cov_ratio, 2)
        f["pos_contrib"] = round(contrib_sum, 3)
        # 前十大重仓解释了多少当日涨跌
        f["explained_pct"] = (round(contrib_sum / f["chg"] * 100, 1)
                              if abs(f["chg"]) > 0.01 else None)
        ranked = [s for s in f["positions"] if s.get("contrib") is not None]
        ranked.sort(key=lambda x: -x["contrib"])
        f["top_pull"] = ranked[0] if ranked else None      # 最大正贡献
        f["top_drag"] = ranked[-1] if ranked else None     # 最大负贡献
        f["n_lhb"] = sum(1 for s in f["positions"] if s["on_lhb"])
        f["n_hot"] = sum(1 for s in f["positions"] if s["is_hot"])

    # ── 组合级：穿透后的个股暴露（按基金市值加权）────────────
    expo = defaultdict(lambda: {"name": "", "mv": 0.0, "chg": None,
                                "funds": [], "board": "", "on_lhb": False,
                                "is_hot": False, "theme": ""})
    for f in funds:
        for s in f["positions"]:
            e = expo[s["code"]]
            e["name"] = s["name"]
            e["mv"] += f["mv"] * s["ratio"] / 100
            e["chg"] = s.get("chg")
            e["board"] = s.get("board", "")
            e["on_lhb"] = e["on_lhb"] or s["on_lhb"]
            e["is_hot"] = e["is_hot"] or s["is_hot"]
            e["theme"] = e["theme"] or s.get("theme", "")
            e["funds"].append(f["name"])
    stocks = []
    for code, e in expo.items():
        stocks.append({"code": code, "name": e["name"], "mv": e["mv"],
                       "chg": e["chg"], "board": e["board"],
                       "on_lhb": e["on_lhb"], "is_hot": e["is_hot"],
                       "theme": e["theme"], "n_funds": len(e["funds"]),
                       "funds": e["funds"],
                       "pnl": (e["mv"] * e["chg"] / 100) if e["chg"] is not None else None})
    stocks.sort(key=lambda x: -x["mv"])

    # ── 组合级：行业暴露 ─────────────────────────────────
    bexpo = defaultdict(float)
    for s in stocks:
        if s["board"]:
            bexpo[s["board"]] += s["mv"]
    boards = [{"name": k, "mv": v,
               "chg": board_map[k]["chg"] if k in board_map else None,
               "rank": board_map[k]["rank"] if k in board_map else None}
              for k, v in bexpo.items()]
    boards.sort(key=lambda x: -x["mv"])

    # ── 组合级：题材暴露（重仓股命中的同花顺题材标签）────────
    texpo = defaultdict(lambda: {"mv": 0.0, "stocks": []})
    for s in stocks:
        if not s["theme"]:
            continue
        for t in {x.strip() for x in s["theme"].split("+") if x.strip()}:
            texpo[t]["mv"] += s["mv"]
            texpo[t]["stocks"].append({"code": s["code"], "name": s["name"],
                                       "chg": s["chg"]})
    themes = [{"tag": k, "mv": v["mv"], "stocks": v["stocks"]}
              for k, v in texpo.items()]
    themes.sort(key=lambda x: -x["mv"])

    # ── 贡献榜（穿透到组合层面的盈亏拉动）──────────────────
    withpnl = [s for s in stocks if s["pnl"] is not None]
    pull = sorted(withpnl, key=lambda x: -x["pnl"])[:8]
    drag = sorted(withpnl, key=lambda x: x["pnl"])[:8]

    # 与市场对照：组合当日 vs 主要指数
    idx = {i["name"]: i["chg"] for i in market["index"]}
    port = fund_data["portfolio"]
    bench = idx.get("沪深300")
    port["excess_hs300"] = (round(port["day_pct"] - bench, 2)
                            if bench is not None else None)

    return {"stocks": stocks, "boards": boards, "themes": themes,
            "pull": pull, "drag": drag,
            "n_lhb": sum(1 for s in stocks if s["on_lhb"]),
            "n_hot": sum(1 for s in stocks if s["is_hot"]),
            "n_stocks": len(stocks),
            "penetrated_mv": sum(s["mv"] for s in stocks)}


def make_narrative(fund_data, attr, market):
    """生成一句话归因结论"""
    port = fund_data["portfolio"]
    d = port["day_pct"]
    mk = market["market"]
    parts = []

    tone = "上涨" if d > 0 else ("下跌" if d < 0 else "持平")
    parts.append(f"组合当日{tone} <b class='{_c(d)}'>{d:+.2f}%</b>"
                 f"（{_money(port['day_pnl'], 1)}）")

    if port.get("excess_hs300") is not None:
        e = port["excess_hs300"]
        parts.append(f"相对沪深300 <b class='{_c(e)}'>{e:+.2f}pct</b>"
                     f"{'跑赢' if e > 0 else '跑输' if e < 0 else '持平'}")

    parts.append(f"全市场涨跌 {mk['up']}/{mk['down']}")

    if attr["pull"] and attr["pull"][0]["pnl"] > 0:
        p = attr["pull"][0]
        parts.append(f"穿透后最大拉动 <b>{p['name']}</b>"
                     f"（<b class='{_c(p['chg'])}'>{p['chg']:+.2f}%</b>）")
    if attr["drag"] and attr["drag"][0]["pnl"] < 0:
        g = attr["drag"][0]
        parts.append(f"最大拖累 <b>{g['name']}</b>"
                     f"（<b class='{_c(g['chg'])}'>{g['chg']:+.2f}%</b>）")
    if attr["n_lhb"]:
        parts.append(f"重仓股中 <b>{attr['n_lhb']}</b> 只当日登上龙虎榜")
    if attr["n_hot"]:
        parts.append(f"<b>{attr['n_hot']}</b> 只入选同花顺强势股")
    return "；".join(parts) + "。"


def _c(v):
    return "up" if v > 0 else ("down" if v < 0 else "flat")


def _money(v, sign=False):
    a = abs(v)
    s = "+" if (sign and v > 0) else ("-" if v < 0 else "")
    if a >= 1e8:
        return f"{s}¥{a/1e8:,.2f}亿"
    if a >= 1e4:
        return f"{s}¥{a/1e4:,.2f}万"
    return f"{s}¥{a:,.0f}"
