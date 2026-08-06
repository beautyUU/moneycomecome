#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股市场情绪日报 + 基金持仓追踪 —— 每日流水线主入口

用法：
    python3 daily_report.py                 # 自动取最近交易日
    python3 daily_report.py 2026-07-24      # 指定交易日
    python3 daily_report.py --no-fund       # 只出市场情绪日报
"""
import os
import sys
import json
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from common import resolve_date, REPORT_DIR, DATA_DIR          # noqa: E402
import market as M                                              # noqa: E402
import fund as F                                                # noqa: E402
import funds_api as FA                                          # noqa: E402
from attribute import attribute, make_narrative                 # noqa: E402
import render as R                                              # noqa: E402

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.log")


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    want_fund = "--no-fund" not in flags

    t0 = time.time()
    date, ok = resolve_date(args[0] if args else None)
    log("=" * 62)
    log(f"A股日报流水线启动 · 目标交易日 {date}")

    if not ok:
        log(f"× {date} 非交易日，跳过（周末/节假日不生成日报）")
        return 0

    # ── 市场数据 ──
    log("[1/5] 市场数据")
    mkt = M.build_market(date, log=log, stock_detail=False)
    m = mkt["market"]
    log(f"   全市场 涨{m['up']}/跌{m['down']} · 行业{len(mkt['boards'])}个")

    # ── 基金全量数据（排行榜 + 内嵌交互）──
    log("[2/5] 基金全量数据")
    fdb = None
    try:
        fdb = FA.build_universe(date, log=log)
        s = fdb["summary"]
        log(f"   基金全量 {s['n']} 只 · 上涨 {s['up_ratio']:.1f}% · "
            f"领涨 {s['best'][1][:12]} {s['best'][2]:+.2f}%")
    except Exception as e:
        log(f"   ! 基金全量数据获取失败：{e}")

    # ── 基金持仓 ──
    fdata = attr = narrative = None
    if want_fund:
        log("[3/5] 基金持仓")
        F.ensure_holdings(sample=True)
        try:
            fdata = F.build_funds(date, log=log)
        except Exception as e:
            log(f"   ! 基金模块异常：{e}")
            traceback.print_exc()
        if fdata:
            log("[4/5] 归因分析")
            attr = attribute(fdata, mkt)
            narrative = make_narrative(fdata, attr, mkt)
            p = fdata["portfolio"]
            log(f"   组合 {p['n']}只 市值¥{p['mv']:,.0f} "
                f"当日{p['day_pct']:+.2f}% 累计{p['pnl_pct']:+.2f}%")
            log(f"   穿透 {attr['n_stocks']} 只个股")
        else:
            log("   （无持仓数据，仅生成基金榜单日报）")
    else:
        log("[3-4/5] 跳过基金模块（--no-fund）")

    # ── 渲染 ──
    log("[5/5] 渲染 HTML")
    html = R.render(mkt, fdata, attr, narrative, fdb)
    out = os.path.join(REPORT_DIR, f"基金日报_{date}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    # 稳定入口：每天覆盖，作为 GitHub Pages 固定地址（显示最新交易日）
    idx = os.path.join(REPORT_DIR, "index.html")
    with open(idx, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"   已写入稳定入口 index.html")

    # 快照留档（供历史对比）
    snap = {"date": date, "generated": datetime.now().isoformat(timespec="seconds"),
            "market": mkt["market"],
            "index": mkt["index"],
            "top_boards": [{"name": b["name"], "chg": b["chg"]} for b in mkt["boards"][:5]],
            "bottom_boards": [{"name": b["name"], "chg": b["chg"]} for b in mkt["boards"][-5:]],
            "fund_summary": fdb["summary"] if fdb else None}
    if fdata:
        snap["portfolio"] = fdata["portfolio"]
        snap["funds"] = [{"code": f["code"], "name": f["name"], "nav": f["nav"],
                          "chg": f["chg"], "mv": f["mv"], "pnl": f["pnl"],
                          "pnl_pct": f["pnl_pct"]} for f in fdata["funds"]]
    hist_dir = os.path.join(DATA_DIR, "history")
    os.makedirs(hist_dir, exist_ok=True)
    json.dump(snap, open(os.path.join(hist_dir, f"{date}.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)

    size = os.path.getsize(out) / 1024
    log(f"✓ 完成 → {out}  ({size:.0f} KB, 用时 {time.time()-t0:.0f}s)")
    log("=" * 62)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
