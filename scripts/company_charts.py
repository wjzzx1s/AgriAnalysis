#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""逐公司画像的图表片段（LaTeX）与作图数据。

本模块只负责"把已有数据画成图"：
  price_chart(r)       月度收盘价 + ZigZag 周期骨架
  fin_chart(r)         近年重要财务指标图：左上 营业收入/归母净利润（柱）、
                       右上 ROE/资产负债率（折线）、下方 货币资金/有息负债（柱）
                       与经营活动现金流净额（折线）；年报 2021---2025 + 2026 年半年报
  fin_table(r)         关键财务指标表（含货币资金、有息负债、现金短债比）
  financing_table(r)   历史融资明细表（来自事实底稿，无底稿时不出表）

口径约定：年报为 2021---2025 年，半年报为 2026 年 6 月末/2026 年上半年（未年化）。
图中 2026 年半年报与年报之间在横轴上留出间隔、以斜纹或空心点区分，题注注明未年化。
"""
from __future__ import annotations

import re

import numpy as np

from make_company import tex_escape

ZZ_PCT = 0.25

# 年报年份（图表左半部分）与半年报在横轴上的位置（与年报留出间隔）
H1_X = 5.7


# ---------------------------------------------------------------- 数值格式
def _fmt(v, nd=1, dash="---"):
    try:
        f = float(v)
        if not np.isfinite(f):
            return dash
        return f"{f:,.{nd}f}"
    except (TypeError, ValueError):
        return dash


def _axis_range(vals, pad_lo=0.10, pad_hi=0.12):
    """按数据范围给出 (ymin, ymax)，并保证 0 在范围内（柱状图需要）。"""
    v = []
    for x in vals:
        if x is None:
            continue
        try:
            f = float(x)
        except (TypeError, ValueError):
            continue
        if np.isfinite(f):
            v.append(f)
    if not v:
        return 0.0, 1.0
    lo, hi = min(v), max(v)
    lo, hi = min(lo, 0.0), max(hi, 0.0)
    if hi == lo:
        hi = lo + 1.0
    span = hi - lo
    return lo - pad_lo * span, hi + pad_hi * span


# ---------------------------------------------------------------- 股价图
def price_chart(r: dict) -> str:
    px = r["px"]
    x0 = px.index[0].year + (px.index[0].month - 0.5) / 12.0
    x1 = px.index[-1].year + (px.index[-1].month - 0.5) / 12.0
    y0, y1 = r["低"] * 0.93, r["高"] * 1.07
    years = list(range(px.index[0].year, px.index[-1].year + 1))
    zz_path = f"data/clean/profiles/pxzz_{r['代码']}.dat"
    px_path = f"data/clean/profiles/px_{r['代码']}.dat"
    nm = tex_escape(r["名称"])
    return "\n".join([
        r"\begin{center}",
        r"\begin{minipage}{\textwidth}\centering",   # 图与题注同页
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=12.6cm, height=3.9cm, scale only axis," ,
        f"  xmin={x0 - 0.12:.3f}, xmax={x1 + 0.18:.3f}, ymin={y0:.2f}, ymax={y1:.2f},",
        "  xtick={" + ",".join(str(y) for y in years) + "},",
        "  yearticks,",
        r"  yticklabel style={font=\scriptsize},",
        r"  ylabel={元/股}, ylabel style={font=\scriptsize},",
        r"  grid=major, grid style={LightGray, line width=0.3pt},",
        r"  axis line style={InkGray, line width=0.5pt},",
        r"  every axis plot/.append style={line width=0.9pt},",
        r"]",
        rf"\addplot[AgriGreen] table[x=x,y=y]{{{px_path}}};",
        rf"\addplot[SoftRed, dashed, line width=0.7pt] table[x=x,y=y]{{{zz_path}}};",
        rf"\addplot[only marks, mark=*, mark size=1.1pt, SoftRed] table[x=x,y=y]{{{zz_path}}};",
        r"\end{axis}",
        r"\end{tikzpicture}",
        "",
        rf"\captionof{{figure}}[{nm}（{r['代码']}）股价与周期骨架]{{"
        rf"{nm}（{r['代码']}）月度收盘价（元/股）与 ZigZag 周期骨架"
        rf"（阈值 {ZZ_PCT * 100:.0f}\%，圆点为周期转折点）}}",
        r"\end{minipage}",
        r"\end{center}",
    ])


# ---------------------------------------------------------------- 财务双联图
def fin_chart(r: dict) -> str:
    """近年主要财务指标组合图（年报 2021---2025 + 2026 年半年报）。

    布局：上排两个子图（营业收入/归母净利润；ROE/资产负债率），下方一个宽子图。
    下方子图里 货币资金/有息负债 用左轴柱状，经营活动现金流净额 用**右轴**蓝点折线：
    现金流与负债规模常差一个量级，若同轴会把蓝点压在零线上，看不出属于哪条序列。
    右轴用 scale only axis + 与左轴相同的宽高、并把绘图区东南角对齐，保证两轴严格重合。
    """
    fin = r.get("fin") or {}
    ann, h1 = fin.get("annual", {}), fin.get("h1", {})
    years = sorted(ann.keys())
    nm, code = tex_escape(r["名称"]), r["代码"]
    fa = f"data/clean/profiles/fin_{code}.dat"
    fh = f"data/clean/profiles/finh_{code}.dat"

    yA = _axis_range([ann[y].get("rev") for y in years] + [h1.get("rev")]
                     + [ann[y].get("ni") for y in years] + [h1.get("ni")])
    yB = _axis_range([ann[y].get("roe") for y in years] + [h1.get("roe")]
                     + [ann[y].get("debt") for y in years] + [h1.get("debt")],
                     pad_lo=0.08, pad_hi=0.10)
    yC = _axis_range([ann[y].get(k) for y in years for k in ("cash", "ibd")]
                     + [h1.get(k) for k in ("cash", "ibd")])
    yD = _axis_range([ann[y].get("ocf") for y in years] + [h1.get("ocf")],
                     pad_lo=0.26, pad_hi=0.30)
    xt = ",".join(str(i) for i in range(len(years))) + f",{H1_X}"
    h1_lab = "2026H1"
    xtl = ",".join(years) + "," + h1_lab

    L = [
        r"\begin{center}",
        r"\begin{minipage}{\textwidth}\centering",   # 不可分页：两图与题注必须同页
        r"\begin{tikzpicture}",
        r"\begin{groupplot}[",
        r"  group style={group size=2 by 1, horizontal sep=0.60cm},",
        r"  width=6.85cm, height=4.60cm,",
        r"  tick label style={font=\tiny},",
        r"  title style={font=\scriptsize\heiti},",
        r"  yticklabel style={font=\tiny},",
        r"  ylabel style={font=\tiny},",
        r"  grid=major, grid style={LightGray, line width=0.3pt},",
        r"  axis line style={InkGray, line width=0.5pt},",
        r"  enlarge x limits={abs=0.8},",
        r"  legend style={font=\scriptsize, at={(0.5,-0.20)}, anchor=north,",
        r"                legend columns=2, draw=none, fill=none, column sep=6pt},",
        r"]",
        # ---------- A：营业收入与归母净利润
        r"\nextgroupplot[",
        r"  ybar, bar width=4pt,",
        f"  ymin={yA[0]:.2f}, ymax={yA[1]:.2f},",
        f"  xtick={{{xt}}},",
        f"  xticklabels={{{xtl}}},",
        r"  ylabel={亿元},",
        r"]",
        rf"\addplot[fill=AgriGreen!75, draw=AgriGreen, bar shift=-2.6pt] table[x=i, y=rev]{{{fa}}};",
        rf"\addplot[fill=SoftRed!60, draw=SoftRed, bar shift=2.6pt] table[x=i, y=ni]{{{fa}}};",
        rf"\addplot[fill=AgriGreen!30, draw=AgriGreen, pattern=north east lines,"
        rf" bar shift=-2.6pt] table[x=x, y=rev]{{{fh}}};",
        rf"\addplot[fill=SoftRed!20, draw=SoftRed, pattern=north east lines,"
        rf" bar shift=2.6pt] table[x=x, y=ni]{{{fh}}};",
        r"\legend{营业收入（年/半年）, 归母净利润（年/半年）}",
        # ---------- B：ROE 与资产负债率
        r"\nextgroupplot[",
        f"  ymin={yB[0]:.1f}, ymax={yB[1]:.1f},",
        f"  xtick={{{xt}}},",
        f"  xticklabels={{{xtl}}},",
        r"  ylabel={\%},",
        r"]",
        rf"\addplot[AgriGold, mark=*, mark size=1.3pt] table[x=i, y=roe]{{{fa}}};",
        rf"\addplot[OilBlue, mark=square*, mark size=1.3pt] table[x=i, y=debt]{{{fa}}};",
        rf"\addplot[only marks, AgriGold, mark=*, mark size=2.0pt] table[x=x, y=roe]{{{fh}}};",
        rf"\addplot[only marks, OilBlue, mark=square*, mark size=2.0pt] table[x=x, y=debt]{{{fh}}};",
        r"\legend{ROE, 资产负债率}",
        r"\end{groupplot}",
        r"\end{tikzpicture}",
        r"\begin{tikzpicture}",
        # ---------- C：货币资金与有息负债（左轴柱状）
        r"\begin{axis}[",
        r"  name=finbot,",
        r"  width=13.75cm, height=3.10cm, scale only axis,",
        f"  ymin={yC[0]:.2f}, ymax={yC[1]:.2f},",
        f"  xtick={{{xt}}},",
        f"  xticklabels={{{xtl}}},",
        r"  tick label style={font=\tiny},",
        r"  yticklabel style={font=\tiny},",
        r"  ylabel={亿元}, ylabel style={font=\tiny},",
        r"  ybar, bar width=4pt,",
        r"  grid=major, grid style={LightGray, line width=0.3pt},",
        r"  axis line style={InkGray, line width=0.5pt},",
        r"  enlarge x limits={abs=0.8},",
        r"  legend style={font=\scriptsize, at={(0.5,-0.26)}, anchor=north,",
        r"                legend columns=2, draw=none, fill=none, column sep=10pt},",
        r"]",
        rf"\addplot[fill=AgriGreen!55, draw=AgriGreen, bar shift=-3.0pt] table[x=i, y=cash]{{{fa}}};",
        rf"\addplot[fill=SoftRed!45, draw=SoftRed, bar shift=3.0pt] table[x=i, y=ibd]{{{fa}}};",
        rf"\addplot[fill=AgriGreen!25, draw=AgriGreen, pattern=north east lines, bar shift=-3.0pt]"
        rf" table[x=x, y=cash]{{{fh}}};",
        rf"\addplot[fill=SoftRed!20, draw=SoftRed, pattern=north east lines, bar shift=3.0pt]"
        rf" table[x=x, y=ibd]{{{fh}}};",
        r"\legend{货币资金（左轴）, 有息负债（左轴）}",
        r"\end{axis}",
        # ---------- D：经营活动现金流净额（右轴蓝点折线）
        r"\begin{axis}[",
        r"  at={(finbot.south east)}, anchor=south east,",
        r"  width=13.75cm, height=3.10cm, scale only axis,",
        r"  axis y line*=right, axis x line*=none, xtick=\empty,",
        f"  ymin={yD[0]:.2f}, ymax={yD[1]:.2f},",
        r"  tick label style={font=\tiny},",
        r"  yticklabel style={font=\tiny}, scaled y ticks=false,",
        r"  legend style={font=\scriptsize, at={(0.5,-0.44)}, anchor=north,",
        r"                legend columns=1, draw=none, fill=none},",
        r"]",
        rf"\addplot[OilBlue, mark=*, mark size=2.2pt, line width=1.3pt] table[x=i, y=ocf]{{{fa}}};",
        rf"\addplot[only marks, OilBlue, mark=*, mark size=3.2pt] table[x=x, y=ocf]{{{fh}}};",
        r"\legend{经营活动现金流净额（右轴，亿元，蓝点）}",
        r"\end{axis}",
        r"\end{tikzpicture}",
        "",
        rf"\captionof{{figure}}[{nm}（{code}）近年主要财务指标]{{"
        rf"{nm}（{code}）近年主要财务指标（左上：营业收入与归母净利润；右上：ROE 与资产负债率；"
        rf"下：货币资金、有息负债为左轴柱状，经营活动现金流净额为其右轴的蓝点折线。",
        rf"2021---2025 年为年报口径，2026H1 为 2026 年半年报/半年末，与其前一年报之间留出间隔、"
        rf"以斜纹或空心点区分；半年报数据未年化）}}",
        r"\end{minipage}",
        r"\end{center}",
    ]
    return "\n".join(L)


# ---------------------------------------------------------------- 财务表
FIN_ROWS = [("营业收入（亿元）", "营收亿", 2), ("归母净利润（亿元）", "归母亿", 2),
            ("毛利率（\\%）", "毛利率", 1), ("ROE（\\%）", "ROE", 1),
            ("资产负债率（\\%）", "负债率", 1),
            ("经营活动现金流净额（亿元）", "现金流亿", 2),
            ("货币资金（亿元）", "货币资金亿", 2),
            ("有息负债合计（亿元）", "有息负债亿", 2),
            ("现金短债比（倍）", "现金短债比", 2)]


def fin_table(r: dict) -> str:
    cols = [("20231231", "2023 年"), ("20241231", "2024 年"), ("20251231", "2025 年"),
            ("20250630", "2025 年半年报"), ("20260630", "2026 年半年报")]
    nm = tex_escape(r["名称"])
    L = [r"\begin{center}\small\setlength{\tabcolsep}{3.4pt}",
         rf"\captionof{{table}}[{nm}（{r['代码']}）关键财务指标]{{"
         rf"{nm}（{r['代码']}）关键财务指标（合并报表口径；两个半年报期均未年化；"
         rf"现金短债比 $=$ 货币资金 $\div$ 短期债务）}}",
         r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}lrrrrr@{}}", r"\toprule",
         "指标 & " + " & ".join(c[1] for c in cols) + r" \\", r"\midrule"]
    for label, key, nd in FIN_ROWS:
        vals = []
        for p, _ in cols:
            v = r.get(key, {}).get(p, np.nan) if isinstance(r.get(key), dict) else np.nan
            vals.append(_fmt(v, nd))
        L.append(label + " & " + " & ".join(vals) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}", r"\end{center}"]
    return "\n".join(L)


def compact_amounts(t: str) -> str:
    """把长数字串折算成更短的金额单位（表格列宽有限）。

    底稿里的披露原文常写出 2,665,599,933.30 元 这样的完整数字，
    在 p{} 窄列里会断成 4---6 行、把表格撑到跨页并顶出下边距；
    这里把“元”按亿元/万元折算（保留两位小数），其余原样保留。
    """
    def repl(m):
        num = float(m.group(1).replace(",", ""))
        unit = m.group(2)
        if unit == "元":
            if num >= 1e8:
                return f"{num / 1e8:.2f} 亿元"
            if num >= 1e4:
                return f"{num / 1e4:.2f} 万元"
            return f"{num:,.0f} 元"
        if unit == "万元":
            return f"{num / 1e4:.2f} 亿元" if num >= 1e4 else f"{num:,.2f} 万元"
        return m.group(0)
    return re.sub(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(亿元|万元|元)", repl, t)


# ---------------------------------------------------------------- 融资明细表
def financing_table(r: dict, rows: list) -> str:
    """历史融资明细表（rows 为事实底稿的融资历史条目）。"""
    nm = tex_escape(r["名称"])
    L = [r"\begin{center}\small\setlength{\tabcolsep}{4pt}",
         rf"\captionof{{table}}[{nm}（{r['代码']}）历史融资与资本运作]{{"
         rf"{nm}（{r['代码']}）历史融资与资本运作（据公司公告与公开报道整理；"
         rf"金额为披露值，含首次公开发行、再融资、债券、银行借款与重整投资等）}}",
         r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}p{1.45cm}p{2.55cm}p{4.05cm}p{4.95cm}@{}}", r"\toprule",
         r"时间 & 方式 & 规模 & 用途与说明 \\", r"\midrule"]
    def brk(txt: str, limit: int = 46) -> str:
        """先归一到子句边界（无省略号），再转义，最后在逗号/顿号后插可断点（长数字串否则不折行）。"""
        import company_digest as DG
        txt = DG.shorten(DG.money(DG.tidy(str(txt))), limit)
        out = tex_escape(txt)
        for ch in ("，", ",", "、", "/"):
            out = out.replace(ch, ch + r"\allowbreak{}")
        return out

    for it in rows:
        t = brk(it.time or "---")
        kind = tex_escape(it.kind or "---")
        scale = brk(it.scale if it.scale else "").strip() or "---"
        # 先按长度截断、再转义：若先转义再切片，可能把 "\\%" 切一半，
        # 留下悬空的反斜杠（如 "10\\……"）而报 Undefined control sequence
        note = "；".join(x for x in (it.use, it.note) if x) or it.text
        note = brk(note, 40)          # 子句边界收缩，不加省略号（行长收短，减少表格越界）
        L.append(f"{t} & {kind} & {scale} & {note} \\\\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}", r"\end{center}"]
    return "\n".join(L)
