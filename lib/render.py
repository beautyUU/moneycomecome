# -*- coding: utf-8 -*-
"""渲染层：基金版单文件 HTML（全内联，可离线打开）

面向「只在支付宝买基金、不买股票」的用户：
  · 00 我的持仓 · 收益与归因（基于官方净值 + 季报前十大重仓）
  · 01 基金自选追踪（可交互：输入基金代码 → 查询 + 加入追踪，数据全内嵌离线可用）
  · 02 市场概览 · 基金赚钱效应
  · 03 基金排行榜（日涨幅 / 近1周 / 近1月 / 近1年 × 类型，可交互切换）
  · 04 行业轮动 · 影响我基金的板块
  · 05 基金类型表现分布
"""
from datetime import datetime
from html import escape as esc
import json

# 基金记录列序（与 funds_api.FUND_DB.all 一致）
# 0 代码 1 名称 2 类型 3 单位净值 4 净值日期 5 日涨跌 6 近1周 7 近1月 8 近1年
DAY, W1, M1, Y1 = 5, 6, 7, 8


# ── 格式化 ───────────────────────────────────────────────
def money(v, sign=False):
    a = abs(v)
    s = "+" if (sign and v > 0) else ("-" if v < 0 else "")
    if a >= 1e8:
        return f"{s}¥{a/1e8:,.2f}亿"
    if a >= 1e4:
        return f"{s}¥{a/1e4:,.2f}万"
    return f"{s}¥{a:,.0f}"


def cls(v):
    if v is None:
        return "flat"
    return "up" if v > 0 else ("down" if v < 0 else "flat")


def pv(v, digits=2, suffix="%"):
    return "—" if v is None else f"{v:+.{digits}f}{suffix}"


def pct(v):
    return "—" if v is None else f"{v:+.2f}%"


# ══════════════ SVG：基金模块 ══════════════
def svg_fund_chg(funds, port):
    rowh, pad_t, pad_l, w = 26, 34, 210, 1000
    h = pad_t + rowh * (len(funds) + 1) + 14
    mx = max([abs(f["chg"]) for f in funds] + [abs(port["day_pct"]), 0.5]) * 1.15
    cx = pad_l + (w - pad_l - 120) / 2
    half = (w - pad_l - 120) / 2
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="各基金当日净值涨跌"><text x="0" y="16" class="ct">'
         f'各基金当日净值涨跌<tspan class="cts">  ·  条宽为涨跌幅，右侧为当日盈亏金额</tspan></text>']
    p.append(f'<line x1="{cx}" y1="{pad_t-8}" x2="{cx}" y2="{h-10}" class="axisline"/>')
    for i, f in enumerate(funds):
        y = pad_t + i * rowh
        bl = half * abs(f["chg"]) / mx
        x0 = cx if f["chg"] > 0 else cx - bl
        c = "bar-up" if f["chg"] > 0 else "bar-dn"
        nm = f["name"][:15]
        p.append(f'<text x="{pad_l-8}" y="{y+15}" class="lbl" text-anchor="end">{esc(nm)}</text>')
        p.append(f'<rect x="{x0:.1f}" y="{y+4}" width="{max(bl,1.5):.1f}" height="15" rx="2" '
                 f'class="{c}"><title>{esc(f["name"])} {f["chg"]:+.2f}% · 权重{f["weight"]}% · '
                 f'当日{money(f["day_pnl"],1)}</title></rect>')
        tx = cx + bl + 7 if f["chg"] > 0 else cx - bl - 7
        anc = "start" if f["chg"] > 0 else "end"
        p.append(f'<text x="{tx:.1f}" y="{y+16}" class="val {cls(f["chg"])}" '
                 f'text-anchor="{anc}">{f["chg"]:+.2f}%</text>')
        p.append(f'<text x="{w-4}" y="{y+16}" class="val {cls(f["day_pnl"])}" '
                 f'text-anchor="end">{money(f["day_pnl"],1)}</text>')
    y = pad_t + len(funds) * rowh + 4
    bl = half * abs(port["day_pct"]) / mx
    x0 = cx if port["day_pct"] > 0 else cx - bl
    p.append(f'<line x1="{pad_l-100}" y1="{y-2}" x2="{w}" y2="{y-2}" class="grid"/>')
    p.append(f'<text x="{pad_l-8}" y="{y+16}" class="lbl bold" text-anchor="end">组合加权</text>')
    p.append(f'<rect x="{x0:.1f}" y="{y+5}" width="{max(bl,1.5):.1f}" height="15" rx="2" '
             f'class="{"bar-up" if port["day_pct"]>0 else "bar-dn"}" opacity="1"/>')
    tx = cx + bl + 7 if port["day_pct"] > 0 else cx - bl - 7
    anc = "start" if port["day_pct"] > 0 else "end"
    p.append(f'<text x="{tx:.1f}" y="{y+17}" class="val bold {cls(port["day_pct"])}" '
             f'text-anchor="{anc}">{port["day_pct"]:+.2f}%</text>')
    p.append(f'<text x="{w-4}" y="{y+17}" class="val bold {cls(port["day_pnl"])}" '
             f'text-anchor="end">{money(port["day_pnl"],1)}</text>')
    p.append("</svg>")
    return "\n".join(p)


def svg_contrib(pull, drag):
    items = [x for x in pull if x["pnl"] > 0][:7]
    negs = [x for x in drag if x["pnl"] < 0][:7]
    n = max(len(items), len(negs))
    if n == 0:
        return ""
    rowh, pad_t, w = 25, 50, 1000
    h = pad_t + rowh * n + 18
    cx = w / 2
    mx = max([abs(x["pnl"]) for x in items + negs] + [1])
    half = cx - 130
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="穿透个股盈亏贡献"><text x="0" y="16" class="ct">'
         f'穿透持股 · 当日盈亏贡献<tspan class="cts">  ·  基金市值 × 占净值比例 × 个股涨跌，'
         f'仅统计前十大重仓</tspan></text>']
    p.append(f'<text x="{cx-136}" y="40" class="hd-up" text-anchor="end">▲ 拉动 TOP{len(items)}</text>')
    p.append(f'<text x="{cx+136}" y="40" class="hd-dn">拖累 TOP{len(negs)} ▼</text>')
    p.append(f'<line x1="{cx-130}" y1="{pad_t-8}" x2="{cx-130}" y2="{h-14}" class="axisline"/>')
    p.append(f'<line x1="{cx+130}" y1="{pad_t-8}" x2="{cx+130}" y2="{h-14}" class="axisline"/>')
    for i in range(n):
        y = pad_t + i * rowh
        if i < len(items):
            s = items[i]
            bl = half * abs(s["pnl"]) / mx
            p.append(f'<rect x="{cx-130-bl:.1f}" y="{y+3}" width="{max(bl,1.5):.1f}" height="15" '
                     f'rx="2" class="bar-up"><title>{esc(s["name"])} {s["chg"]:+.2f}% · '
                     f'贡献{money(s["pnl"],1)} · 穿透市值{money(s["mv"])}</title></rect>')
            p.append(f'<text x="{cx-130-bl-7:.1f}" y="{y+15}" class="val up" text-anchor="end">'
                     f'{money(s["pnl"],1)}</text>')
            p.append(f'<text x="{cx-124}" y="{y+15}" class="lbl">{esc(s["name"])}</text>')
            p.append(f'<text x="{cx-124+len(s["name"])*13+8}" y="{y+15}" class="sub">'
                     f'<tspan class="up">{s["chg"]:+.2f}%</tspan></text>')
        if i < len(negs):
            s = negs[i]
            bl = half * abs(s["pnl"]) / mx
            p.append(f'<rect x="{cx+130}" y="{y+3}" width="{max(bl,1.5):.1f}" height="15" '
                     f'rx="2" class="bar-dn"><title>{esc(s["name"])} {s["chg"]:+.2f}% · '
                     f'贡献{money(s["pnl"],1)} · 穿透市值{money(s["mv"])}</title></rect>')
            p.append(f'<text x="{cx+130+bl+7:.1f}" y="{y+15}" class="val down">{money(s["pnl"],1)}</text>')
            p.append(f'<text x="{cx+124}" y="{y+15}" class="lbl" text-anchor="end">{esc(s["name"])}</text>')
            p.append(f'<text x="{cx+124-len(s["name"])*13-8}" y="{y+15}" class="sub" text-anchor="end">'
                     f'<tspan class="down">{s["chg"]:+.2f}%</tspan></text>')
    p.append("</svg>")
    return "\n".join(p)


def svg_expo(boards, total_mv, top=12):
    its = boards[:top]
    if not its:
        return ""
    rowh, pad_t, pad_l, w = 25, 34, 150, 1000
    h = pad_t + rowh * len(its) + 14
    mx = max(x["mv"] for x in its) or 1
    bw = w - pad_l - 250
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="组合行业暴露"><text x="0" y="16" class="ct">'
         f'组合行业暴露 TOP{len(its)}<tspan class="cts">  ·  条长为穿透市值，右侧为该行业当日涨跌与全市场排名</tspan></text>']
    for i, b in enumerate(its):
        y = pad_t + i * rowh
        bl = bw * b["mv"] / mx
        pctv = b["mv"] / total_mv * 100 if total_mv else 0
        p.append(f'<text x="{pad_l-8}" y="{y+15}" class="lbl" text-anchor="end">{esc(b["name"])}</text>')
        p.append(f'<rect x="{pad_l}" y="{y+4}" width="{max(bl,2):.1f}" height="15" rx="2" '
                 f'class="bar-expo"><title>{esc(b["name"])} · 穿透市值{money(b["mv"])} · '
                 f'占组合{pctv:.1f}%</title></rect>')
        p.append(f'<text x="{pad_l+bl+8:.1f}" y="{y+16}" class="val">{money(b["mv"])}</text>')
        p.append(f'<text x="{pad_l+bl+86:.1f}" y="{y+16}" class="sub">占{pctv:.1f}%</text>')
        if b["chg"] is not None:
            p.append(f'<text x="{w-70}" y="{y+16}" class="val {cls(b["chg"])}" text-anchor="end">'
                     f'{b["chg"]:+.2f}%</text>')
            p.append(f'<text x="{w-4}" y="{y+16}" class="sub" text-anchor="end">'
                     f'第{b["rank"]}名</text>')
    p.append("</svg>")
    return "\n".join(p)


# ══════════════ SVG：市场模块 ══════════════
def svg_industry(boards, n=15):
    if not boards:
        return ""
    n = min(n, len(boards) // 2 or 1)
    tp, bt = boards[:n], boards[-n:][::-1]
    rowh, pad_t, w = 25, 52, 1000
    cx = w / 2
    h = pad_t + rowh * n + 24
    mx = max([abs(b["chg"]) for b in tp + bt]) or 1
    half = cx - 118
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="行业板块涨跌幅排名"><text x="0" y="16" class="ct">'
         f'行业板块涨跌幅排名<tspan class="cts">  ·  东财行业分类 {len(boards)} 个板块 · 流通市值加权</tspan></text>']
    p.append(f'<text x="{cx-124}" y="40" class="hd-up" text-anchor="end">▲ 领涨 TOP{n}</text>')
    p.append(f'<text x="{cx+124}" y="40" class="hd-dn">领跌 TOP{n} ▼</text>')
    p.append(f'<line x1="{cx-118}" y1="{pad_t-8}" x2="{cx-118}" y2="{h-20}" class="axisline"/>')
    p.append(f'<line x1="{cx+118}" y1="{pad_t-8}" x2="{cx+118}" y2="{h-20}" class="axisline"/>')
    for i in range(n):
        y = pad_t + i * rowh
        if i < len(tp):
            b = tp[i]
            bl = half * abs(b["chg"]) / mx
            c = "bar-up" if b["chg"] > 0 else "bar-dn"
            p.append(f'<rect x="{cx-118-bl:.1f}" y="{y+3}" width="{max(bl,1.5):.1f}" height="15" '
                     f'rx="2" class="{c}"><title>{esc(b["name"])} {b["chg"]:+.2f}% · '
                     f'涨{b["up"]}跌{b["down"]} · 领涨 {esc(b["leader"]["name"])}</title></rect>')
            p.append(f'<text x="{cx-118-bl-7:.1f}" y="{y+15}" class="val {cls(b["chg"])}" '
                     f'text-anchor="end">{b["chg"]:+.2f}%</text>')
            p.append(f'<text x="{cx-112}" y="{y+15}" class="lbl">{esc(b["name"])}</text>')
            p.append(f'<text x="{cx-112+len(b["name"])*13+6}" y="{y+15}" class="sub">'
                     f'<tspan class="up">{b["up"]}</tspan>/<tspan class="down">{b["down"]}</tspan>'
                     f' · {esc(b["leader"]["name"])}</text>')
        if i < len(bt):
            b = bt[i]
            bl = half * abs(b["chg"]) / mx
            c = "bar-up" if b["chg"] > 0 else "bar-dn"
            p.append(f'<rect x="{cx+118}" y="{y+3}" width="{max(bl,1.5):.1f}" height="15" '
                     f'rx="2" class="{c}"><title>{esc(b["name"])} {b["chg"]:+.2f}% · '
                     f'涨{b["up"]}跌{b["down"]} · 领跌 {esc(b["lagger"]["name"])}</title></rect>')
            p.append(f'<text x="{cx+118+bl+7:.1f}" y="{y+15}" class="val {cls(b["chg"])}">'
                     f'{b["chg"]:+.2f}%</text>')
            p.append(f'<text x="{cx+112}" y="{y+15}" class="lbl" text-anchor="end">{esc(b["name"])}</text>')
            p.append(f'<text x="{cx+112-len(b["name"])*13-6}" y="{y+15}" class="sub" text-anchor="end">'
                     f'<tspan class="up">{b["up"]}</tspan>/<tspan class="down">{b["down"]}</tspan></text>')
    p.append("</svg>")
    return "\n".join(p)


def svg_breadth(mk, total=None, label="全市场涨跌分布"):
    w, h = 1000, 74
    up, dn, fl = mk["up"], mk["down"], mk["flat"]
    tot = max(up + dn + fl, 1)
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="{label}"><text x="0" y="14" class="ct">'
         f'{label}<tspan class="cts">  ·  样本 {tot} 只</tspan></text>']
    x, y, bh = 0, 26, 24
    for n, c, lb in ((up, "bar-up", "上涨"), (fl, "bar-flat", "平盘"), (dn, "bar-dn", "下跌")):
        ww = w * n / tot
        p.append(f'<rect x="{x:.1f}" y="{y}" width="{ww:.1f}" height="{bh}" class="{c}">'
                 f'<title>{lb} {n} 只 · {n/tot*100:.1f}%</title></rect>')
        if ww > 62:
            p.append(f'<text x="{x+ww/2:.1f}" y="{y+16}" class="inbar" text-anchor="middle">'
                     f'{lb} {n} · {n/tot*100:.0f}%</text>')
        x += ww
    p.append(f'<text x="0" y="{y+bh+18}" class="sub">上涨占比 '
             f'<tspan class="{"up" if up>dn else "down"}">{up/max(tot,1)*100:.1f}%</tspan>'
             f'　涨跌比 <tspan class="{"up" if up>dn else "down"}">{up/max(dn,1):.2f}</tspan></text>')
    p.append("</svg>")
    return "\n".join(p)


def svg_fund_breadth(summary):
    up, dn, fl = summary["up"], summary["down"], summary["flat"]
    return svg_breadth({"up": up, "down": dn, "flat": fl},
                       label=f"基金涨跌分布（全部 {summary['n']} 只开放式基金）")


def svg_fund_rank(records, idx, label):
    """基金排行榜条形图（前 15）"""
    its = records[:15]
    if not its:
        return ""
    rowh, pad_t, pad_l, w = 25, 34, 168, 1000
    h = pad_t + rowh * len(its) + 14
    mx = max([abs(r[idx]) for r in its if r[idx] is not None] + [0.5]) * 1.1
    cx = pad_l + (w - pad_l - 150) / 2
    half = (w - pad_l - 150) / 2
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="{label}"><text x="0" y="16" class="ct">'
         f'{label}<tspan class="cts">  ·  前 {len(its)} 名（红涨绿跌）</tspan></text>']
    p.append(f'<line x1="{cx}" y1="{pad_t-8}" x2="{cx}" y2="{h-10}" class="axisline"/>')
    for i, r in enumerate(its):
        y = pad_t + i * rowh
        v = r[idx] if r[idx] is not None else 0
        bl = half * abs(v) / mx
        x0 = cx if v >= 0 else cx - bl
        c = "bar-up" if v >= 0 else "bar-dn"
        nm = r[1][:16]
        p.append(f'<text x="{pad_l-8}" y="{y+15}" class="lbl" text-anchor="end">{esc(nm)}</text>')
        p.append(f'<text x="{pad_l-8}" y="{y+15}" class="code" '
                 f'text-anchor="end" dx="0" style="display:none"></text>')
        p.append(f'<rect x="{x0:.1f}" y="{y+4}" width="{max(bl,1.5):.1f}" height="15" rx="2" '
                 f'class="{c}"><title>{esc(r[1])} {r[0]} · {pct(v)}</title></rect>')
        tx = cx + bl + 7 if v >= 0 else cx - bl - 7
        anc = "start" if v >= 0 else "end"
        p.append(f'<text x="{tx:.1f}" y="{y+16}" class="val {cls(v)}" '
                 f'text-anchor="{anc}">{pct(v)}</text>')
        p.append(f'<text x="{w-4}" y="{y+16}" class="code" text-anchor="end">{r[0]}</text>')
    p.append("</svg>")
    return "\n".join(p)


def svg_type_dist(type_dist):
    its = type_dist
    if not its:
        return ""
    rowh, pad_t, pad_l, w = 30, 40, 110, 1000
    h = pad_t + rowh * len(its) + 14
    mx = max([abs(t[3]) for t in its] + [0.5]) * 1.15
    cx = pad_l + (w - pad_l - 130) / 2
    half = (w - pad_l - 130) / 2
    p = [f'<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg" '
         f'role="img" aria-label="基金类型表现分布"><text x="0" y="16" class="ct">'
         f'各类型基金当日平均涨跌<tspan class="cts">  ·  条长为平均日涨跌，右侧为数量/上涨只数</tspan></text>']
    p.append(f'<line x1="{cx}" y1="{pad_t-8}" x2="{cx}" y2="{h-10}" class="axisline"/>')
    for i, t in enumerate(its):
        y = pad_t + i * rowh
        v = t[3]
        bl = half * abs(v) / mx
        x0 = cx if v >= 0 else cx - bl
        c = "bar-up" if v >= 0 else "bar-dn"
        p.append(f'<text x="{pad_l-8}" y="{y+16}" class="lbl" text-anchor="end">{esc(t[1])}</text>')
        p.append(f'<rect x="{x0:.1f}" y="{y+5}" width="{max(bl,1.5):.1f}" height="16" rx="2" '
                 f'class="{c}"><title>{esc(t[1])} · 平均{pct(v)} · {t[2]}只 · 上涨{t[4]}只</title></rect>')
        tx = cx + bl + 7 if v >= 0 else cx - bl - 7
        anc = "start" if v >= 0 else "end"
        p.append(f'<text x="{tx:.1f}" y="{y+17}" class="val {cls(v)}" text-anchor="{anc}">{pct(v)}</text>')
        p.append(f'<text x="{w-4}" y="{y+17}" class="sub" text-anchor="end">'
                 f'{t[2]}只 · 涨{t[4]}</text>')
    p.append("</svg>")
    return "\n".join(p)


# ══════════════ 表格 ══════════════
def tbl_funds(funds):
    r = []
    for f in funds:
        stale = ('<span class="warn" title="该基金净值尚未更新到目标日期">净值滞后</span>'
                 if f["nav_stale"] else "")
        r.append(
            f'<tr><td class="code">{f["code"]}</td>'
            f'<td class="nm">{esc(f["name"])} {stale}</td>'
            f'<td class="num">{f["nav"]:.4f}</td>'
            f'<td class="num {cls(f["chg"])}">{f["chg"]:+.2f}%</td>'
            f'<td class="num {cls(f["day_pnl"])}">{money(f["day_pnl"],1)}</td>'
            f'<td class="num">{f["shares"]:,.0f}</td>'
            f'<td class="num">{f["cost_nav"]:.4f}</td>'
            f'<td class="num">{money(f["mv"])}</td>'
            f'<td class="num bold {cls(f["pnl"])}">{money(f["pnl"],1)}</td>'
            f'<td class="num bold {cls(f["pnl_pct"])}">{f["pnl_pct"]:+.2f}%</td>'
            f'<td class="num">{f["weight"]:.1f}%</td>'
            f'<td class="num dim">{f["nav_date"]}</td></tr>')
    return "\n".join(r)


def tbl_positions(funds):
    r = []
    for f in funds:
        r.append(f'<tr class="grp"><td colspan="7">'
                 f'<b>{esc(f["name"])}</b> <span class="code">{f["code"]}</span>'
                 f'　当日 <b class="{cls(f["chg"])}">{f["chg"]:+.2f}%</b>'
                 f'　前十大合计占净值 <b>{f["pos_coverage"]:.1f}%</b>'
                 f'　估算贡献 <b class="{cls(f["pos_contrib"])}">{f["pos_contrib"]:+.2f}pct</b>'
                 f'　<span class="dim">持仓截止 {f["pos_as_of"] or "—"}</span></td></tr>')
        for s in f["positions"]:
            hk = ('<span class="tag-hk">港股</span>' if s.get("mtype") == "HK" else "")
            r.append(
                f'<tr><td class="code">{s["code"]}</td>'
                f'<td class="nm">{esc(s["name"])}</td>'
                f'<td class="num">{s["ratio"]:.2f}%</td>'
                f'<td class="num {cls(s.get("chg"))}">{pv(s.get("chg"))}</td>'
                f'<td class="num bold {cls(s.get("contrib"))}">'
                f'{pv(s.get("contrib"), 3, "pct")}</td>'
                f'<td class="nm sm">{esc(s.get("board") or "—")}</td>'
                f'<td class="num {cls(s.get("board_chg"))}">{pv(s.get("board_chg"))}</td>'
                f'<td class="rs">{hk or "<span class=nil>—</span>"}</td></tr>')
    return "\n".join(r)


def tbl_penetrate(stocks, total_mv):
    r = []
    for i, s in enumerate(stocks[:40], 1):
        r.append(
            f'<tr><td class="num dim">{i}</td><td class="code">{s["code"]}</td>'
            f'<td class="nm">{esc(s["name"])}</td>'
            f'<td class="num">{money(s["mv"])}</td>'
            f'<td class="num">{s["mv"]/total_mv*100 if total_mv else 0:.2f}%</td>'
            f'<td class="num {cls(s["chg"])}">{pv(s["chg"])}</td>'
            f'<td class="num bold {cls(s["pnl"])}">'
            f'{money(s["pnl"],1) if s["pnl"] is not None else "—"}</td>'
            f'<td class="nm sm">{esc(s["board"] or "—")}</td>'
            f'<td class="num {cls(s.get("board_chg"))}">{pv(s.get("board_chg"))}</td>'
            f'<td class="num dim">{s["n_funds"]}</td></tr>')
    return "\n".join(r)


def tbl_board(boards):
    r = []
    for b in boards:
        r.append(f'<tr><td class="num dim">{b["rank"]}</td><td class="nm">{esc(b["name"])}</td>'
                 f'<td class="num bold {cls(b["chg"])}">{b["chg"]:+.2f}%</td>'
                 f'<td class="num {cls(b["chg_eq"])}">{b["chg_eq"]:+.2f}%</td>'
                 f'<td class="num">{b["n"]}</td><td class="num up">{b["up"]}</td>'
                 f'<td class="num down">{b["down"]}</td>'
                 f'<td class="nm sm">{esc(b["leader"]["name"])} '
                 f'<span class="mini {cls(b["leader"]["chg"])}">{b["leader"]["chg"]:+.2f}%</span></td>'
                 f'<td class="nm sm">{esc(b["lagger"]["name"])} '
                 f'<span class="mini {cls(b["lagger"]["chg"])}">{b["lagger"]["chg"]:+.2f}%</span></td>'
                 f'<td class="num dim">{b["free_mcap_yi"]:,.0f}</td></tr>')
    return "\n".join(r)


def tbl_rank(records, idxs=(DAY, W1, M1, Y1)):
    """基金排行表（全维度）"""
    r = []
    for i, r0 in enumerate(records[:50], 1):
        r.append(
            f'<tr><td class="num dim">{i}</td>'
            f'<td class="code">{r0[0]}</td>'
            f'<td class="nm">{esc(r0[1])}</td>'
            f'<td class="num dim">{r0[2]}</td>'
            f'<td class="num">{r0[3]:.4f}</td>'
            f'<td class="num dim">{r0[4] or ""}</td>'
            f'<td class="num bold {cls(r0[DAY])}">{pct(r0[DAY])}</td>'
            f'<td class="num {cls(r0[W1])}">{pct(r0[W1])}</td>'
            f'<td class="num {cls(r0[M1])}">{pct(r0[M1])}</td>'
            f'<td class="num {cls(r0[Y1])}">{pct(r0[Y1])}</td></tr>')
    return "\n".join(r)


def resolve_rank(fund_db, dim, typ):
    codes = fund_db["rank"][dim][typ]
    m = {r[0]: r for r in fund_db["all"]}
    return [m[c] for c in codes if c in m]


# ══════════════ 交互脚本（纯字符串，避免 f-string 转义）══════
# 基金记录列序：0 代码 1 名称 2 类型 3 净值 4 净值日期 5 日 6 周 7 月 8 年
JS_BODY = r"""
(function(){
 var ALL=FUND_DB.all, MAP={}, TYPES=FUND_DB.types;
 ALL.forEach(function(r){MAP[r[0]]=r;});
 var DIM_LABEL={day:'日涨幅',w1:'近1周',m1:'近1月',y1:'近1年'};
 var DIM_IDX={day:5,w1:6,m1:7,y1:8};
 var CUR_DIM='day', CUR_TYPE='all';
 function esc(s){return (''+s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
 function cls(v){return v==null?'flat':(v>0?'up':(v<0?'down':'flat'));}
 function pct(v){return v==null?'—':(v>=0?'+':'')+v.toFixed(2)+'%';}
 function nav(v){return v==null?'—':v.toFixed(4);}
 function fdate(v){if(!v)return '';v=''+v;return v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8);}
 function resolveRank(d,t){return (FUND_DB.rank[d][t]||[]).map(function(c){return MAP[c];}).filter(Boolean);}

 function rankSVG(its,idx,label){
  if(!its.length) return '';
  var rowh=25,padT=34,padL=168,w=1000,h=padT+rowh*its.length+14;
  var vals=its.map(function(r){return r[idx]==null?0:r[idx];});
  var mx=Math.max.apply(null,vals.map(Math.abs).concat([0.5]))*1.1;
  var cx=padL+(w-padL-150)/2, half=(w-padL-150)/2, s='';
  s+='<svg viewBox="0 0 '+w+' '+h+'" class="chart" xmlns="http://www.w3.org/2000/svg" role="img">';
  s+='<text x="0" y="16" class="ct">'+label+'<tspan class="cts">  ·  前 '+its.length+' 名（红涨绿跌）</tspan></text>';
  s+='<line x1="'+cx+'" y1="'+(padT-8)+'" x2="'+cx+'" y2="'+(h-10)+'" class="axisline"/>';
  its.forEach(function(r,i){
   var y=padT+i*rowh, v=r[idx]==null?0:r[idx];
   var bl=half*Math.abs(v)/mx, x0=v>=0?cx:cx-bl, c=v>=0?'bar-up':'bar-dn', nm=r[1].slice(0,16);
   s+='<text x="'+(padL-8)+'" y="'+(y+15)+'" class="lbl" text-anchor="end">'+esc(nm)+'</text>';
   s+='<rect x="'+x0.toFixed(1)+'" y="'+(y+4)+'" width="'+Math.max(bl,1.5).toFixed(1)+'" height="15" rx="2" class="'+c+'"><title>'+esc(r[1])+' '+r[0]+' · '+pct(v)+'</title></rect>';
   var tx=v>=0?cx+bl+7:cx-bl-7, anc=v>=0?'start':'end';
   s+='<text x="'+tx.toFixed(1)+'" y="'+(y+16)+'" class="val '+cls(v)+'" text-anchor="'+anc+'">'+pct(v)+'</text>';
   s+='<text x="'+(w-4)+'" y="'+(y+16)+'" class="code" text-anchor="end">'+r[0]+'</text>';
  });
  s+='</svg>';
  return s;
 }
 function rankRows(recs){
  return recs.slice(0,50).map(function(r,i){
   return '<tr><td class="num dim">'+(i+1)+'</td><td class="code">'+r[0]+'</td>'
    +'<td class="nm">'+esc(r[1])+'</td><td class="num dim">'+r[2]+'</td>'
    +'<td class="num">'+nav(r[3])+'</td><td class="num dim">'+fdate(r[4])+'</td>'
    +'<td class="num bold '+cls(r[5])+'">'+pct(r[5])+'</td>'
    +'<td class="num '+cls(r[6])+'">'+pct(r[6])+'</td>'
    +'<td class="num '+cls(r[7])+'">'+pct(r[7])+'</td>'
    +'<td class="num '+cls(r[8])+'">'+pct(r[8])+'</td></tr>';
  }).join('');
 }
 function renderRank(){
  var recs=resolveRank(CUR_DIM,CUR_TYPE), idx=DIM_IDX[CUR_DIM];
  var tl=CUR_TYPE==='all'?'全部类型':(TYPES[CUR_TYPE]||CUR_TYPE);
  document.getElementById('rankSvg').innerHTML=rankSVG(recs.slice(0,15),idx,'基金'+DIM_LABEL[CUR_DIM]+' TOP15（'+tl+'）');
  document.getElementById('rankTbl').getElementsByTagName('tbody')[0].innerHTML=rankRows(recs);
  var c=document.getElementById('rcnt'); if(c)c.textContent='共 '+recs.length+' 只（显示前 '+Math.min(50,recs.length)+'）';
 }
 function setDim(d){CUR_DIM=d;[].forEach.call(document.querySelectorAll('.tools .chip[data-d]'),function(c){c.classList.toggle('on',c.getAttribute('data-d')===d);});renderRank();}
 function setType(t){CUR_TYPE=t;[].forEach.call(document.querySelectorAll('.tools .chip[data-t]'),function(c){c.classList.toggle('on',c.getAttribute('data-t')===t);});renderRank();}

 var KEY='fund_watch', MEM=null, PERSIST=true;
 function loadW(){ if(MEM) return MEM; try{ MEM=JSON.parse(localStorage.getItem(KEY))||[]; }catch(e){ MEM=[]; PERSIST=false; } return MEM; }
 function saveW(){ if(!PERSIST)return; try{ localStorage.setItem(KEY, JSON.stringify(MEM)); }catch(e){ PERSIST=false; } }
 function getW(){ return loadW(); }
 function setW(a){ MEM=a; saveW(); }
 function onRank(code){var out=[];['day','w1','m1','y1'].forEach(function(d){var arr=FUND_DB.rank[d];for(var t in arr){if(arr[t].indexOf(code)>=0){out.push(DIM_LABEL[d]+'·'+(t==='all'?'全部':(TYPES[t]||t)));break;}}});return out.slice(0,4);}
 function addWatch(code){code=(''+code).trim();if(!MAP[code])return;var a=getW();if(a.indexOf(code)<0){a.push(code);setW(a);}renderWatch();var b=document.querySelector('#detail .btn');if(b){b.textContent='✓ 已加入自选追踪';b.disabled=true;b.style.opacity=.6;}}
 function rmWatch(code){setW(getW().filter(function(c){return c!==code;}));renderWatch();}
 function clearWatch(){if(confirm('清空全部自选追踪？')){setW([]);renderWatch();}}
 function exportWatch(){var a=getW();if(!a.length){alert('暂无可导出的追踪码');return;}var txt=a.join(',');if(navigator.clipboard)navigator.clipboard.writeText(txt);alert('已复制 '+a.length+' 个基金代码：\n'+txt+'\n\n可粘贴进 config/holdings.csv 第1列（基金代码）以加入完整归因。');}
 function detailHTML(r){
  var badges=onRank(r[0]).map(function(b){return '<span class="wc-badge">'+b+'</span>';}).join(' ');
  return '<div class="dc"><div><span class="dname">'+esc(r[1])+'</span><span class="dcode">'+r[0]
   +'</span><span class="wc-t">'+(TYPES[r[2]]||r[2])+'</span></div>'
   +'<div class="dgrid">'
   +'<div class="dcell"><div class="dl">单位净值</div><div class="dv">'+nav(r[3])+'</div></div>'
   +'<div class="dcell"><div class="dl">净值日期</div><div class="dv" style="font-size:13px">'+fdate(r[4])+'</div></div>'
   +'<div class="dcell"><div class="dl">日涨跌</div><div class="dv '+cls(r[5])+'">'+pct(r[5])+'</div></div>'
   +'<div class="dcell"><div class="dl">近1周</div><div class="dv '+cls(r[6])+'">'+pct(r[6])+'</div></div>'
   +'<div class="dcell"><div class="dl">近1月</div><div class="dv '+cls(r[7])+'">'+pct(r[7])+'</div></div>'
   +'<div class="dcell"><div class="dl">近1年</div><div class="dv '+cls(r[8])+'">'+pct(r[8])+'</div></div>'
   +'</div>'+(badges?'<div style="margin-top:8px">'+badges+'</div>':'')
   +'<div class="dbtn"><button class="btn" onclick="addWatch(\''+r[0]+'\')">加入自选追踪</button></div></div>';
 }
 function pick(code){var r=MAP[code];if(!r)return;document.getElementById('fq').value=code;document.getElementById('suggest').className='suggest';document.getElementById('detail').innerHTML=detailHTML(r);}
 function pickFirst(){var d=document.querySelector('#suggest div');if(d)d.click();}
 function suggest(){
  var q=document.getElementById('fq').value.trim().toLowerCase(), box=document.getElementById('suggest');
  if(!q){box.className='suggest';box.innerHTML='';return;}
  var mt=[];
  for(var i=0;i<ALL.length && mt.length<8;i++){var r=ALL[i];if(r[0]===q||r[0].indexOf(q)===0||r[1].toLowerCase().indexOf(q)>=0)mt.push(r);}
  if(!mt.length){box.innerHTML='<div style="color:var(--dim);padding:8px 11px">未找到匹配基金</div>';box.className='suggest show';return;}
  box.innerHTML=mt.map(function(r){return '<div onclick="pick(\''+r[0]+'\')"><span class="sc">'+r[0]+'</span>'+esc(r[1])+'<span class="st">'+(TYPES[r[2]]||r[2])+'</span></div>';}).join('');
  box.className='suggest show';
 }
 function renderWatch(){
  var a=getW(), el=document.getElementById('watch');
  var wc=document.getElementById('wcnt'); if(wc)wc.textContent=a.length?('共 '+a.length+' 只'):'';
  if(!a.length){el.innerHTML='<div class="note" style="margin:0">还没有追踪的基金。在上方输入代码查询后点「加入追踪」即可。</div>';return;}
  el.innerHTML=a.map(function(code){var r=MAP[code];if(!r)return '';
   var badges=onRank(code).map(function(b){return '<span class="wc-badge">'+b+'</span>';}).join(' ');
   return '<div class="wcard"><span class="wc-x" onclick="rmWatch(\''+code+'\')">×</span>'
    +'<div><span class="wc-n">'+esc(r[1])+'</span><span class="wc-c">'+r[0]+'</span><span class="wc-t">'+(TYPES[r[2]]||r[2])+'</span></div>'
    +'<div class="wc-r">'
    +'<div class="x"><div class="k">单位净值</div><div class="v">'+nav(r[3])+'</div></div>'
    +'<div class="x"><div class="k">日涨跌</div><div class="v '+cls(r[5])+'">'+pct(r[5])+'</div></div>'
    +'<div class="x"><div class="k">近1月</div><div class="v '+cls(r[7])+'">'+pct(r[7])+'</div></div>'
    +'<div class="x"><div class="k">近1年</div><div class="v '+cls(r[8])+'">'+pct(r[8])+'</div></div>'
    +'</div>'+(badges?('<div style="margin-top:7px">'+badges+'</div>'):'')+'</div>';
  }).join('');
 }
 window.suggest=suggest; window.pick=pick; window.pickFirst=pickFirst;
 window.setDim=setDim; window.setType=setType; window.addWatch=addWatch;
 window.rmWatch=rmWatch; window.clearWatch=clearWatch; window.exportWatch=exportWatch;
 document.addEventListener('DOMContentLoaded',function(){renderRank();renderWatch();});
 document.addEventListener('click',function(e){var b=document.getElementById('suggest');if(b&&!e.target.closest('.tbox'))b.className='suggest';});
})();
"""


# ══════════════ 主渲染 ══════════════
def render(mkt, fdata=None, attr=None, narrative=None, fund_db=None):
    date = mkt["date"]
    dt = datetime.strptime(date, "%Y-%m-%d")
    date_cn = f"{dt.year}年{dt.month}月{dt.day}日"
    week = "周" + "一二三四五六日"[dt.weekday()]
    boards = mkt["boards"]
    mk = mkt["market"]
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    b_up = sum(1 for b in boards if b["chg"] > 0)

    idx_html = "\n".join(
        f'<div class="idx"><span class="in">{esc(x["name"])}</span>'
        f'<span class="ip">{x["close"]:,.2f}</span>'
        f'<span class="ic {cls(x["chg"])}">{x["chg"]:+.2f}%</span></div>'
        for x in mkt["index"])

    summ = fund_db["summary"] if fund_db else None

    # ── 00 持仓区 ──
    fund_html = ""
    if fdata and attr:
        p = fdata["portfolio"]
        funds = fdata["funds"]
        ex = p.get("excess_hs300")
        exs = (f'<span class="{cls(ex)}">{ex:+.2f}pct</span>' if ex is not None else "—")
        stale_note = (f'<div class="warn-box">⚠ 有 <b>{p["stale"]}</b> 只基金的净值尚未更新到 {date}'
                      f'（场外基金净值通常在交易日 20:00-23:00 披露），表中已标注实际净值日期，'
                      f'当日盈亏可能不完整。</div>' if p["stale"] else "")
        kpi_f = [
            ("持仓市值", money(p["mv"]), "", f'{p["n"]} 只基金 · 成本 {money(p["cost"])}', "neutral"),
            ("当日盈亏", money(p["day_pnl"], 1), f'{p["day_pct"]:+.2f}%',
             f'涨 {p["day_up"]} / 跌 {p["day_down"]}', cls(p["day_pnl"])),
            ("累计盈亏", money(p["pnl"], 1), f'{p["pnl_pct"]:+.2f}%',
             f'盈利 {p["win"]} / 亏损 {p["lose"]}', cls(p["pnl"])),
            ("超额收益", exs.replace('<span class="', '<span class="k'), "vs沪深300",
             f'组合 {p["day_pct"]:+.2f}% · 沪深300 '
             f'{next((i["chg"] for i in mkt["index"] if i["name"]=="沪深300"), 0):+.2f}%',
             cls(ex) if ex is not None else "neutral"),
            ("穿透个股", str(attr["n_stocks"]), "只",
             "仅前十大重仓 · 估算贡献", "neutral"),
            ("穿透市值", money(attr["penetrated_mv"]), "",
             f'占组合 {attr["penetrated_mv"]/p["mv"]*100 if p["mv"] else 0:.0f}%', "neutral"),
        ]
        kpi_f_html = "\n".join(
            f'<div class="kpi {c}"><div class="kl">{l}</div>'
            f'<div class="kv">{v}<span class="ku">{u}</span></div>'
            f'<div class="kd">{d}</div></div>' for l, v, u, d, c in kpi_f)
        fund_html = f"""
<section class="hl">
 <div class="sh"><span class="no">00</span><h2>我的持仓 · 收益与归因</h2>
  <span class="src">数据源 <b>天天基金净值 + 季报前十大重仓 + 当日行情</b></span></div>
 <div class="sbody">
  <div class="kpis">{kpi_f_html}</div>
  {stale_note}
  <div class="narr">{narrative}</div>
  {svg_fund_chg(funds, p)}
  <div class="tw"><table><thead><tr>
   <th>代码</th><th>基金名称</th><th class="num">单位净值</th><th class="num">当日</th>
   <th class="num">当日盈亏</th><th class="num">持有份额</th><th class="num">成本单价</th>
   <th class="num">持仓市值</th><th class="num">累计盈亏</th><th class="num">收益率</th>
   <th class="num">权重</th><th class="num">净值日期</th>
  </tr></thead><tbody>{tbl_funds(funds)}</tbody></table></div>

  {svg_contrib(attr["pull"], attr["drag"])}
  {svg_expo(attr["boards"], attr["penetrated_mv"])}

  <div class="cols">
   <div><div class="colt">穿透持股 TOP40（按穿透市值）</div>
    <div class="tw scroll" style="max-height:330px"><table><thead><tr>
     <th class="num">#</th><th>代码</th><th>名称</th><th class="num">穿透市值</th>
     <th class="num">占比</th><th class="num">当日</th><th class="num">盈亏贡献</th>
     <th>所属行业</th><th class="num">行业当日</th><th class="num">基金数</th>
    </tr></thead><tbody>{tbl_penetrate(attr["stocks"], attr["penetrated_mv"])}</tbody></table></div></div>
   <div><div class="colt">组合行业暴露（前十大重仓股所属行业）</div>
    <div class="tw scroll" style="max-height:330px"><table><thead><tr>
     <th>行业板块</th><th class="num">穿透市值</th><th class="num">当日涨跌</th><th class="num">排名</th>
    </tr></thead><tbody>{"".join(
      f'<tr><td class="nm">{esc(b["name"])}</td><td class="num">{money(b["mv"])}</td>'
      f'<td class="num {cls(b["chg"])}">{pct(b["chg"])}</td>'
      f'<td class="num dim">{b["rank"]}</td></tr>' for b in attr["boards"][:12])}</tbody></table></div></div>
  </div>

  <div class="colt" style="margin-top:12px">各基金前十大重仓股明细与归因</div>
  <div class="tw scroll" style="max-height:520px"><table><thead><tr>
   <th>代码</th><th>股票名称</th><th class="num">占净值</th><th class="num">当日涨跌</th>
   <th class="num">估算贡献</th><th>所属行业</th><th class="num">行业当日</th><th>市场</th>
  </tr></thead><tbody>{tbl_positions(funds)}</tbody></table></div>
 </div>
</section>"""
    else:
        fund_html = f"""
<section class="hl">
 <div class="sh"><span class="no">00</span><h2>我的持仓 · 收益与归因</h2>
  <span class="src">数据源 <b>天天基金净值 + 季报前十大重仓</b></span></div>
 <div class="sbody"><div class="note">尚未配置持仓。请在 <b>config/holdings.csv</b> 中按
  <b>基金代码,基金名称,持有份额,成本单价,买入日期</b> 填写你的基金，重跑日报即可看到
  「持仓市值 / 累计盈亏 / 当日盈亏 / 穿透持股归因」。<br>
  也可以直接在下方 <b>01 基金自选追踪</b> 中输入基金代码先体验查询与跟踪。</div></div>
</section>"""

    # ── 01 自选追踪（可交互）──
    if fund_db:
        track_html = f"""
<section>
 <div class="sh"><span class="no">01</span><h2>基金自选追踪（可交互）</h2>
  <span class="src">全部 {summ['n']} 只基金数据已内嵌 · 离线可用</span></div>
 <div class="sbody">
  <div class="note">输入 <b>基金代码</b>（6 位）或 <b>名称关键词</b> 即时查询净值与阶段业绩；
   点「加入追踪」可把基金加入本机自选（localStorage 持久保存），下次打开仍在。
   <br><b>关于完整归因</b>：下方追踪只展示行情与业绩；若要像「00 我的持仓」那样看到
   <b>成本盈亏、穿透持股</b>，请把代码加入 <b>config/holdings.csv</b> 后重跑日报（见 01 内「导出追踪码」）。</div>
  <div class="track">
   <div class="tbox">
    <input id="fq" placeholder="输入基金代码或名称，如 005827 / 沪深300" autocomplete="off"
      oninput="suggest()" onkeydown="if(event.key==='Enter')pickFirst()">
    <div id="suggest" class="suggest"></div>
   </div>
   <div id="detail" class="detail"></div>
  </div>
  <div class="twbar">
   <span class="colt" style="margin:0">我的自选追踪</span>
   <span class="cnt" id="wcnt"></span>
   <button class="btn" onclick="exportWatch()">导出追踪码</button>
   <button class="btn ghost" onclick="clearWatch()">清空</button>
  </div>
  <div id="watch" class="watch"></div>
 </div>
</section>"""
    else:
        track_html = """
<section><div class="sh"><span class="no">01</span><h2>基金自选追踪（可交互）</h2></div>
 <div class="sbody"><div class="warn-box">基金全量数据获取失败，交互式追踪暂不可用。</div></div></section>"""

    # ── 02 市场概览 · 基金赚钱效应 ──
    if summ:
        kpi_m = [
            ("上涨基金占比", f'{summ["up_ratio"]:.1f}%', "",
             f'涨 {summ["up"]} / 跌 {summ["down"]} / 平 {summ["flat"]}', "up" if summ["up"] > summ["down"] else "down"),
            ("当日平均涨跌", f'{summ["avg"]:+.2f}%', "",
             f'中位数 {summ["median"]:+.2f}%', cls(summ["avg"])),
            ("领涨基金", summ["best"][1][:14], f'{summ["best"][2]:+.2f}%',
             f'代码 {summ["best"][0]}', "up"),
            ("领跌基金", summ["worst"][1][:14], f'{summ["worst"][2]:+.2f}%',
             f'代码 {summ["worst"][0]}', "down"),
            ("行业涨跌", f'{b_up}<span class="sep">/</span>{len(boards)-b_up}', "涨/跌",
             f'共 {len(boards)} 个行业板块', "up" if b_up > len(boards) / 2 else "down"),
            ("全市场涨跌", f'{mk["up"]}<span class="sep">/</span>{mk["down"]}', "涨/跌",
             f'涨停态{mk["limit_up_like"]} · 跌停态{mk["limit_down_like"]}',
             "up" if mk["up"] > mk["down"] else "down"),
        ]
        kpi_m_html = "\n".join(
            f'<div class="kpi {c}"><div class="kl">{l}</div>'
            f'<div class="kv">{v}<span class="ku">{u}</span></div>'
            f'<div class="kd">{d}</div></div>' for l, v, u, d, c in kpi_m)
        overview = f"""
<section>
 <div class="sh"><span class="no">02</span><h2>市场概览 · 基金赚钱效应</h2>
  <span class="src">基金样本 <b>{summ['n']}</b> 只开放式基金（天天基金）</span></div>
 <div class="sbody"><div class="kpis">{kpi_m_html}</div>
  {svg_fund_breadth(summ)}
 </div>
</section>"""
    else:
        overview = ""

    # ── 03 基金排行榜（可交互）──
    if fund_db:
        default = resolve_rank(fund_db, "day", "all")
        chips = "".join(
            f'<span class="chip {"on" if t=="all" else ""}" data-t="{t}" onclick="setType(\'{t}\')">{l}</span>'
            for t, l in [("all", "全部")] + [(k, fund_db["types"][k]) for k in fund_db["types"]])
        tabs = "".join(
            f'<span class="chip {"on" if d=="day" else ""}" data-d="{d}" onclick="setDim(\'{d}\')">{l}</span>'
            for d, l in [("day", "日涨幅"), ("w1", "近1周"), ("m1", "近1月"), ("y1", "近1年")])
        rank_html = f"""
<section>
 <div class="sh"><span class="no">03</span><h2>基金排行榜</h2>
  <span class="src">数据源 <b>天天基金全量排行</b> · 点击切换维度与类型</span></div>
 <div class="sbody">
  <div class="tools">
   <span class="tl">维度</span>{tabs}
   <span class="tl" style="margin-left:10px">类型</span>{chips}
   <span class="cnt" id="rcnt"></span>
  </div>
  <div id="rankSvg">{svg_fund_rank(default, DAY, "基金日涨幅 TOP15（全部类型）")}</div>
  <div class="tw scroll"><table id="rankTbl"><thead><tr>
   <th class="num">#</th><th>代码</th><th>基金名称</th><th class="num">类型</th>
   <th class="num">单位净值</th><th class="num">净值日期</th><th class="num">日涨跌</th>
   <th class="num">近1周</th><th class="num">近1月</th><th class="num">近1年</th>
  </tr></thead><tbody>{tbl_rank(default)}</tbody></table></div>
 </div>
</section>"""
    else:
        rank_html = ""

    # ── 04 行业轮动 · 影响我的板块 ──
    expo_note = ""
    if fdata and attr and attr["boards"]:
        top = attr["boards"][0]
        expo_note = (f'<div class="note">你持仓基金的前十大重仓股主要暴露于 '
                     f'<b>{len(attr["boards"])}</b> 个行业，其中穿透市值最高的是 '
                     f'<b>{esc(top["name"])}</b>（{money(top["mv"])}，当日 {pct(top["chg"])}）。'
                     f'下方板块涨跌直接影响你基金的净值表现。</div>')
    board_html = f"""
<section>
 <div class="sh"><span class="no">04</span><h2>行业轮动 · 影响我基金的板块</h2>
  <span class="src">数据源 <b>东财行业板块 + 腾讯财经日K</b></span></div>
 <div class="sbody">
  <div class="note">东财行业分类共 <b>{len(boards)}</b> 个板块、{mk["n"]} 只成分股（剔除当日停牌）。
   当日 <b class="up">{b_up}</b> 个板块收红、<b class="down">{len(boards)-b_up}</b> 个收绿。
   基金（尤其行业/主题指数基金）的当日表现，本质上由这些板块涨跌驱动。</div>
  {expo_note}
  {svg_industry(boards)}
  <div class="colt" style="margin-top:6px">全部 {len(boards)} 个行业板块完整排名</div>
  <div class="tw scroll"><table><thead><tr>
   <th class="num">排名</th><th>行业板块</th><th class="num">涨跌幅(加权)</th>
   <th class="num">涨跌幅(等权)</th><th class="num">成分股</th><th class="num">上涨</th>
   <th class="num">下跌</th><th>领涨股</th><th>领跌股</th><th class="num">流通市值(亿)</th>
  </tr></thead><tbody>{tbl_board(boards)}</tbody></table></div>
 </div>
</section>"""

    # ── 05 基金类型表现分布 ──
    if fund_db:
        trows = "".join(
            f'<tr><td class="nm">{esc(t[1])}</td>'
            f'<td class="num">{t[2]:,}</td>'
            f'<td class="num up">{t[4]:,}</td>'
            f'<td class="num {cls(t[3])}">{pct(t[3])}</td></tr>'
            for t in fund_db["type_dist"])
        type_html = f"""
<section>
 <div class="sh"><span class="no">05</span><h2>基金类型表现分布</h2>
  <span class="src">数据源 <b>天天基金全量排行</b></span></div>
 <div class="sbody">
  <div class="note">按投资类型拆分当日<b>平均涨跌</b>与<b>上涨只数</b>，帮你判断当天哪类基金更占优
   （股票/混合/指数弹性大，债券/QDII 相对稳健）。</div>
  {svg_type_dist(fund_db["type_dist"])}
  <div class="tw"><table><thead><tr>
   <th>基金类型</th><th class="num">数量</th><th class="num">当日上涨</th><th class="num">平均涨跌</th>
  </tr></thead><tbody>{trows}</tbody></table></div>
 </div>
</section>"""
    else:
        type_html = ""

    # ── 拼接 ──
    sub = (f'我的持仓 · 基金排行榜 · 自选追踪 · 行业轮动'
           if fund_db else '市场概览 · 行业轮动')
    hsub = (f'基金赚钱效应 <b>{summ["up_ratio"]:.0f}%</b> 上涨；领涨 '
            f'<b class="up">{esc(summ["best"][1][:10])}</b> {summ["best"][2]:+.2f}%'
            if summ else
            f'全市场涨跌 {mk["up"]}/{mk["down"]}')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>基金日报 · {date} · 我的持仓 + 基金排行榜 + 行业轮动</title>
<style>
:root{{
 --bg:#080b11; --bg2:#0d1119; --panel:#111722; --panel2:#151c28;
 --line:#1d2634; --line2:#273244;
 --txt:#dbe2ec; --txt2:#95a3b8; --dim:#5f6b7e;
 --up:#f5455c; --up2:#ff6b7d; --dn:#12b886; --dn2:#2ee6a8;
 --hot:#f5a623; --acc:#4d94ff; --expo:#7c6cf0;
 --mono:"SF Mono",SFMono-Regular,ui-monospace,Menlo,Consolas,"Liberation Mono",monospace;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);
 font:13px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
 -webkit-font-smoothing:antialiased;padding:0 0 40px}}
.wrap{{max-width:1320px;margin:0 auto;padding:0 18px}}
header{{background:linear-gradient(180deg,#0f1622 0%,#0a0e15 100%);
 border-bottom:1px solid var(--line2);padding:20px 0 16px;margin-bottom:16px}}
.htop{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}}
h1{{font-size:21px;font-weight:700;letter-spacing:.4px}} h1 .dot{{color:var(--up)}}
.hdate{{font:600 14px/1 var(--mono);color:var(--hot);background:rgba(245,166,35,.1);
 border:1px solid rgba(245,166,35,.3);padding:5px 10px;border-radius:4px}}
.hsub{{color:var(--txt2);font-size:12px;margin-top:7px}} .hsub b{{color:var(--txt)}}
.idxbar{{display:flex;gap:1px;background:var(--line);border:1px solid var(--line);
 border-radius:5px;overflow:hidden;margin-top:13px;flex-wrap:wrap}}
.idx{{flex:1;min-width:150px;background:var(--panel);padding:8px 11px;display:flex;align-items:baseline;gap:7px}}
.idx .in{{color:var(--txt2);font-size:11.5px}}
.idx .ip{{font:600 13.5px var(--mono);margin-left:auto}}
.idx .ic{{font:600 12px var(--mono);min-width:52px;text-align:right}}
.kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:0 0 14px}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:6px;
 padding:11px 13px 10px;position:relative;overflow:hidden}}
.kpi::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--line2)}}
.kpi.up::before{{background:var(--up)}} .kpi.down::before{{background:var(--dn)}}
.kpi.hot::before{{background:var(--hot)}} .kpi.neutral::before{{background:var(--acc)}}
.kpi.flat::before{{background:var(--dim)}}
.kl{{color:var(--txt2);font-size:11.5px;letter-spacing:.3px}}
.kv{{font:700 20px/1.25 var(--mono);margin:5px 0 4px;word-break:break-all}}
.kpi.up .kv{{color:var(--up)}} .kpi.down .kv{{color:var(--dn)}}
.kpi.hot .kv{{color:var(--hot);font-size:17px}}
.kv .ku{{font-size:11.5px;font-weight:500;color:var(--txt2);margin-left:4px}}
.kv .sep{{color:var(--dim);margin:0 2px}}
.kd{{color:var(--dim);font-size:11px;line-height:1.4}}
section{{background:var(--bg2);border:1px solid var(--line);border-radius:7px;
 margin-bottom:16px;overflow:hidden}}
section.hl{{border-color:#2f3d55;box-shadow:0 0 0 1px rgba(77,148,255,.08)}}
.sh{{display:flex;align-items:center;gap:10px;padding:11px 15px;
 background:var(--panel);border-bottom:1px solid var(--line)}}
section.hl .sh{{background:linear-gradient(90deg,#16203050,#111722)}}
.sh h2{{font-size:14.5px;font-weight:700;letter-spacing:.3px}}
.sh .no{{font:700 11px var(--mono);color:var(--bg);background:var(--acc);padding:2px 7px;border-radius:3px}}
section.hl .sh .no{{background:var(--hot)}}
.sh .src{{margin-left:auto;font-size:11px;color:var(--dim)}} .sh .src b{{color:var(--txt2);font-weight:500}}
.sbody{{padding:14px 15px}}
.note{{font-size:11.5px;color:var(--txt2);background:var(--panel);border-left:2px solid var(--acc);
 padding:7px 11px;border-radius:0 4px 4px 0;margin-bottom:12px;line-height:1.6}}
.narr{{font-size:12.5px;color:var(--txt);background:var(--panel);border-left:2px solid var(--hot);
 padding:10px 13px;border-radius:0 4px 4px 0;margin-bottom:13px;line-height:1.75}}
.warn-box{{font-size:11.5px;color:#f0c674;background:rgba(245,166,35,.07);
 border:1px solid rgba(245,166,35,.2);padding:8px 12px;border-radius:4px;margin-bottom:11px}}
.chart{{width:100%;height:auto;display:block;margin:2px 0 14px;overflow:visible}}
.chart text{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
.ct{{fill:var(--txt);font-size:13px;font-weight:700}}
.cts{{fill:var(--dim);font-size:11px;font-weight:400}}
.lbl{{fill:var(--txt);font-size:12px}} .lbl.bold{{font-weight:700}}
.code{{fill:var(--dim);font-size:10.5px;font-family:var(--mono)}}
.val{{fill:var(--txt);font-size:11.5px;font-weight:600;font-family:var(--mono)}}
.val.bold{{font-weight:700}}
.sub{{fill:var(--dim);font-size:10.5px}}
.axis{{fill:var(--dim);font-size:10px;font-family:var(--mono)}}
.inbar{{fill:#fff;font-size:11px;font-weight:600}}
.grid{{stroke:var(--line);stroke-width:1;stroke-dasharray:2 3}}
.axisline{{stroke:var(--line2);stroke-width:1}}
.hd-up{{fill:var(--up);font-size:11.5px;font-weight:600}}
.hd-dn{{fill:var(--dn);font-size:11.5px;font-weight:600}}
.bar-up{{fill:var(--up);opacity:.85}} .bar-dn{{fill:var(--dn);opacity:.85}}
.bar-flat{{fill:#4a5566}} .bar-hot{{fill:var(--hot);opacity:.82}}
.bar-expo{{fill:var(--expo);opacity:.8}}
.chart rect:hover{{opacity:1;filter:brightness(1.2)}}
svg .up{{fill:var(--up)}} svg .down{{fill:var(--dn)}} svg .flat{{fill:var(--txt2)}}
.tw{{overflow-x:auto;border:1px solid var(--line);border-radius:5px;margin-bottom:4px}}
.tw.scroll{{max-height:560px;overflow-y:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
thead th{{position:sticky;top:0;z-index:2;background:var(--panel2);color:var(--txt2);
 font-weight:600;font-size:11px;text-align:left;padding:8px 9px;white-space:nowrap;
 border-bottom:1px solid var(--line2);letter-spacing:.2px}}
thead th.num{{text-align:right}}
tbody td{{padding:6px 9px;border-bottom:1px solid rgba(29,38,52,.6);vertical-align:middle}}
tbody tr:hover{{background:rgba(77,148,255,.055)}}
tbody tr.grp{{background:var(--panel2)}} tbody tr.grp:hover{{background:var(--panel2)}}
tbody tr.grp td{{padding:8px 9px;font-size:11.5px;color:var(--txt2);
 border-top:1px solid var(--line2)}}
td.num{{text-align:right;font-family:var(--mono);font-size:11.5px;white-space:nowrap}}
td.code{{font-family:var(--mono);font-size:11px;color:var(--txt2)}}
td.nm{{font-weight:600;white-space:nowrap}} td.nm.sm{{font-weight:500;font-size:11.5px}}
td.bold{{font-weight:700}}
td.rs{{color:var(--txt2);font-size:11px;line-height:1.5;min-width:180px}}
.up{{color:var(--up)}} .down{{color:var(--dn)}} .flat{{color:var(--txt2)}}
.hot{{color:var(--hot)}} .dim{{color:var(--dim)}} .nil{{color:#39424f}}
.mini{{font-family:var(--mono);font-size:10px;margin-left:2px}}
.tag-hk{{display:inline-block;background:rgba(124,108,240,.12);border:1px solid rgba(124,108,240,.3);
 color:#a89bff;padding:1px 5px;border-radius:3px;font-size:10.5px;margin:1px 2px 1px 0}}
.warn{{display:inline-block;background:rgba(245,166,35,.12);border:1px solid rgba(245,166,35,.3);
 color:var(--hot);padding:0 5px;border-radius:3px;font-size:10px;font-weight:500}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.colt{{font-size:12px;font-weight:700;color:var(--txt);margin-bottom:8px;
 padding-left:8px;border-left:2px solid var(--hot)}}
.tools{{display:flex;gap:9px;align-items:center;margin-bottom:10px;flex-wrap:wrap}}
.tl{{font-size:11px;color:var(--dim)}}
.tools input{{background:var(--panel);border:1px solid var(--line2);color:var(--txt);
 padding:6px 11px;border-radius:4px;font-size:12px;width:250px;outline:none;font-family:inherit}}
.tools input:focus{{border-color:var(--acc)}}
.tools .cnt{{font-size:11.5px;color:var(--dim)}}
.chip{{background:var(--panel);border:1px solid var(--line2);color:var(--txt2);
 padding:4px 10px;border-radius:12px;font-size:11px;cursor:pointer;user-select:none}}
.chip:hover{{border-color:var(--acc);color:var(--txt)}}
.chip.on{{background:rgba(77,148,255,.16);border-color:var(--acc);color:var(--txt)}}
footer{{margin-top:22px;padding:16px 0 0;border-top:1px solid var(--line);
 color:var(--dim);font-size:11.5px;line-height:1.75}}
footer b{{color:var(--txt2);font-weight:600}}
.srcs{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:11px 0}}
.srcc{{background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:9px 12px}}
.srcc .t{{color:var(--txt);font-weight:600;font-size:12px;margin-bottom:3px}}
.srcc .u{{font-family:var(--mono);font-size:10px;color:var(--acc);word-break:break-all}}
.disc{{background:rgba(245,166,35,.05);border:1px solid rgba(245,166,35,.18);
 border-radius:5px;padding:10px 13px;margin-top:11px;color:var(--txt2);font-size:11px;line-height:1.7}}
/* 自选追踪 */
.track{{display:grid;grid-template-columns:340px 1fr;gap:14px;align-items:start}}
.tbox{{position:relative}}
.tbox input{{width:100%!important}}
.suggest{{position:absolute;left:0;right:0;top:42px;z-index:30;background:var(--panel2);
 border:1px solid var(--line2);border-radius:5px;max-height:300px;overflow-y:auto;display:none}}
.suggest.show{{display:block}}
.suggest div{{padding:8px 11px;cursor:pointer;border-bottom:1px solid rgba(29,38,52,.6);font-size:12px}}
.suggest div:hover{{background:rgba(77,148,255,.1)}}
.suggest .sc{{color:var(--dim);font-family:var(--mono);font-size:10.5px;margin-right:8px}}
.suggest .st{{color:var(--hot);font-size:10.5px;margin-left:6px}}
.detail{{min-height:80px}}
.detail .dc{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:13px 15px}}
.detail .dname{{font-size:15px;font-weight:700}}
.detail .dcode{{color:var(--dim);font-family:var(--mono);font-size:11px;margin-left:8px}}
.detail .dgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:11px}}
.detail .dcell .dl{{color:var(--txt2);font-size:11px}}
.detail .dcell .dv{{font:700 16px/1.3 var(--mono);margin-top:3px}}
.detail .dbtn{{margin-top:12px}}
.btn{{background:rgba(77,148,255,.16);border:1px solid var(--acc);color:var(--txt);
 padding:6px 14px;border-radius:5px;font-size:12px;cursor:pointer;font-family:inherit}}
.btn:hover{{background:rgba(77,148,255,.28)}}
.btn.ghost{{background:transparent;border-color:var(--line2);color:var(--txt2)}}
.btn.ghost:hover{{border-color:var(--dn);color:var(--dn)}}
.btn.sm{{padding:3px 9px;font-size:11px}}
.twbar{{display:flex;align-items:center;gap:10px;margin:16px 0 8px}}
.watch{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}}
.wcard{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:11px 12px;position:relative}}
.wcard .wc-n{{font-weight:700;font-size:13px}}
.wcard .wc-c{{color:var(--dim);font-family:var(--mono);font-size:10.5px;margin-left:6px}}
.wcard .wc-t{{font-size:10.5px;color:var(--hot);margin-left:5px}}
.wcard .wc-r{{display:flex;gap:12px;margin-top:8px}}
.wcard .wc-r .x .k{{color:var(--txt2);font-size:10px}}
.wcard .wc-r .x .v{{font:700 13px var(--mono)}}
.wcard .wc-badge{{display:inline-block;margin-top:7px;font-size:10px;padding:1px 6px;border-radius:3px;
 background:rgba(245,166,35,.12);border:1px solid rgba(245,166,35,.3);color:var(--hot)}}
.wcard .wc-x{{position:absolute;top:8px;right:9px;color:var(--dim);cursor:pointer;font-size:14px}}
.wcard .wc-x:hover{{color:var(--dn)}}
@media(max-width:1100px){{.kpis{{grid-template-columns:repeat(3,1fr)}}.cols{{grid-template-columns:1fr}}
 .srcs{{grid-template-columns:1fr}}.track{{grid-template-columns:1fr}}}}
@media(max-width:640px){{.kpis{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:17px}}}}
</style></head><body>

<header><div class="wrap">
 <div class="htop">
  <h1>基金日报<span class="dot">.</span></h1>
  <span class="hdate">{date} {week}</span>
  <span style="color:var(--dim);font-size:11.5px">{sub}</span>
 </div>
 <div class="hsub">{hsub}</div>
 <div class="idxbar">{idx_html}</div>
</div></header>

<div class="wrap">
{fund_html}
{track_html}
{overview}
{rank_html}
{board_html}
{type_html}
<footer>
 <div style="color:var(--txt);font-size:12.5px;font-weight:600;margin-bottom:3px">数据来源与口径说明</div>
 <div class="srcs">
  <div class="srcc"><div class="t">① 基金净值与排行 · 天天基金</div>
   <div>开放式基金全量排行（rankhandler），{summ['n'] if summ else 0} 只，含单位净值与日/周/月/年阶段收益</div>
   <div class="u">fund.eastmoney.com/data/rankhandler.aspx</div></div>
  <div class="srcc"><div class="t">② 基金净值 · 天天基金</div>
   <div>场外单位净值（f10/lsjz），支付宝等三方平台持有的均为场外份额，一律以官方净值为准</div>
   <div class="u">api.fund.eastmoney.com/f10/lsjz</div></div>
  <div class="srcc"><div class="t">③ 基金持仓 · 天天基金季报</div>
   <div>前十大重仓股及占净值比例（FundArchivesDatas jjcc），季度披露</div>
   <div class="u">fundf10.eastmoney.com/FundArchivesDatas.aspx</div></div>
  <div class="srcc"><div class="t">④ 行业板块 · 东财 + 腾讯</div>
   <div>东财行业板块分类与成分股，个股当日涨跌幅取自腾讯财经前复权日K</div>
   <div class="u">push2delay.eastmoney.com · web.ifzq.gtimg.cn</div></div>
 </div>
 <div class="disc"><b>口径与方法：</b>
  ① 基金排行的「日/周/月/年涨跌」为天天基金披露的单位净值增长率；QDII、部分债券与货币基金的净值披露可能有 1 日滞后。
  ② 基金全量数据（{summ['n'] if summ else 0} 只）已<b>内嵌于本页</b>，因此「01 自选追踪 / 03 基金排行榜」可完全离线交互，无需联网。
  ③ 行业板块涨跌幅由<b>成分股当日前复权日K涨跌幅按流通市值加权</b>重算，与东财官方板块指数可能存在小数级差异。
  ④ 基金归因为估算：重仓股为<b>季报披露的前十大</b>（通常滞后 1-3 个月，仅覆盖部分仓位）；「估算贡献」= 个股当日涨跌 × 季报占净值比例。
  ⑤ 「穿透市值」= 基金持仓市值 × 该股占净值比例，同一只股票被多只基金持有时会合并累加。
  ⑥ 本报告为公开数据整理，<b>不构成任何投资建议</b>。</div>
 <div style="margin-top:11px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
  <span>交易日期 <b>{date_cn}（{week}）</b>　·　生成时间 <b>{gen}</b></span>
  <span>数据来源：<b>天天基金排行/净值/季报</b> / <b>东财行业板块</b>{" / <b>我的持仓归因</b>" if fdata else ""}</span>
 </div>
</footer>
</div>
"""
    if fund_db:
        fund_json = json.dumps(fund_db, ensure_ascii=False)
        html += ('<script id="fund-db">const FUND_DB=' + fund_json
                 + ';</script>\n<script>' + JS_BODY + '</script>\n')
    html += "</body></html>"
    return html
