#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 data/raw/company/<code>_<kind>.csv 加工为第二部分（上市公司画像）所需的数据表。

产出：
  data/clean/company_master.csv    每家公司一行：行业、上市信息、市值、2026 年半年报财务、事件计数
  data/clean/company_events.csv    每家公司一行的公告分类计数（战略转型/融资/风险线索）
  data/clean/company_ind_*.csv     按申万行业汇总
  data/clean/comp_ind_count.dat    行业公司数（tikz）
  data/clean/comp_mktcap.dat       流通市值分布（tikz）
  data/clean/comp_roe.dat          2026 年半年报 ROE 分布（tikz）
  data/clean/comp_growth_scatter.dat  营收同比-净利率散点（tikz）
  tex/gen/company_master.tex       全量公司表（longtable）
  tex/gen/company_by_ind.tex       分行业汇总表
  notes/company_summary.md         汇总统计说明

口径说明：第二部分（上市公司画像）统一采用 **2026 年半年报** 作为财务口径
（合并报表、未年化），2023---2025 年年报数据仅作为趋势对照保留。
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CLEAN, RAW  # noqa: E402

COMP = os.path.join(RAW, "company")
GEN = os.path.join(os.path.dirname(CLEAN), "..", "tex", "gen")
GEN = os.path.abspath(GEN)
NOTES = os.path.join(os.path.dirname(os.path.dirname(CLEAN)), "notes")

# 财务口径：年报（近三年，作趋势对照）与半年报（2026 年半年报为统一口径）
ANNUAL = ("2023", "2024", "2025")
H1 = "20260630"
H1_PREV = "20250630"

# 从财务摘要取用的指标：(接口指标名, 内部字段名)
FA_METRICS = [("营业总收入", "营业收入"), ("归母净利润", "归母净利润"),
              ("净资产收益率(ROE)", "ROE"), ("毛利率", "毛利率"),
              ("销售净利率", "销售净利率"), ("资产负债率", "资产负债率")]

LOG: list[str] = []


def log(s: str = "") -> None:
    LOG.append(s)
    print(s)


def rd(code: str, kind: str) -> pd.DataFrame | None:
    p = os.path.join(COMP, f"{code}_{kind}.csv")
    if not os.path.exists(p):
        return None
    try:
        return pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    except Exception:  # noqa: BLE001
        return None


def num(x) -> float:
    try:
        v = float(str(x).replace(",", "").replace("%", ""))
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def period_name(p: str) -> str:
    """报告期标签 → 中文期次（20260630 → “2026 年半年报”）。"""
    p = str(p)
    if p == H1:
        return "2026 年半年报"
    if p == H1_PREV:
        return "2025 年半年报"
    if p.endswith("1231"):
        return f"{p[:4]} 年年报"
    return p


def fin_ind_at(fi: pd.DataFrame | None, col: str, date: str) -> float:
    """财务指标表（fin_ind）中某一报告期的单个指标值。"""
    if fi is None or not len(fi) or col not in fi.columns:
        return np.nan
    s = fi[fi["日期"].astype(str).str[:10] == date]
    return num(s.iloc[0][col]) if len(s) else np.nan


# ---------------------------------------------------------------- 公告分类规则
EVENT_RULES: list[tuple[str, str]] = [
    ("再融资", r"向特定对象发行|向不特定对象发行|非公开发行|定增|可转换公司债券|配股|发行股份购买|募集说明书|向特定投资者"),
    ("重大重组与并购", r"重大资产重组|收购|兼并|吸收合并|股权转让|出售资产|资产置换|要约收购"),
    ("回购与激励", r"回购|股权激励|员工持股|限制性股票"),
    ("对外投资与转型", r"对外投资|设立(子公司|合资|控股)|战略合作|框架协议|投资协议|产业基金|扩产|技改|扩建|项目建设|产能建设|签约|中标"),
    ("担保与关联交易", r"担保|关联交易|财务资助|委托理财"),
    ("股东行为", r"减持|增持|权益变动|股份质押|解除质押"),
    ("业绩与风险", r"业绩预告|业绩快报|预亏|预增|风险提示|退市|终止上市|立案|问询|诉讼|仲裁|逾期|冻结|被?ST|更正公告"),
]


def classify(title: str) -> list[str]:
    return [name for name, pat in EVENT_RULES if re.search(pat, title or "")]


def build() -> None:
    uni = pd.read_csv(os.path.join(CLEAN, "sw_stock_industry.csv"),
                      encoding="utf-8-sig", dtype=str)
    l1 = uni[uni["行业层级"] == "一级"][["股票代码", "证券名称"]].drop_duplicates("股票代码")
    codes = l1["股票代码"].tolist()
    log(f"# 农业上市公司画像数据（{len(codes)} 家公司）\n")

    # 三级行业映射（缺失时回退到二级、一级）
    def level(code: str, lv: str) -> str:
        s = uni[(uni["股票代码"] == code) & (uni["行业层级"] == lv)]
        return s["行业名称"].iloc[0] if len(s) else ""

    rows, erows = [], []
    for code in codes:
        name = l1[l1["股票代码"] == code]["证券名称"].iloc[0]
        rec = {"代码": code, "名称": name,
               "一级行业": level(code, "一级"), "二级行业": level(code, "二级"),
               "三级行业": level(code, "三级")}

        # --- 公司概况（巨潮）
        p = rd(code, "profile")
        if p is not None and len(p):
            r = p.iloc[0]
            rec["上市日期"] = str(r.get("上市日期", ""))[:10]
            rec["所属市场"] = r.get("所属市场", "")
            rec["注册地"] = str(r.get("注册地址", ""))[:22]
            rec["主营业务"] = str(r.get("主营业务", ""))[:60].replace("\n", " ")
            rec["注册资本万元"] = num(r.get("注册资金", np.nan))

        # --- 行情与市值（新浪日行情 × 流通股本）
        b = rd(code, "basic")
        if b is not None and len(b):
            r = b.iloc[0]
            rec["最新收盘"] = num(r.get("最新收盘价", np.nan))
            rec["流通市值亿元"] = num(r.get("流通市值(元)", np.nan)) / 1e8
            rec["近一年涨跌%"] = num(r.get("近一年涨跌幅%", np.nan))
            rec["行情日期"] = str(r.get("数据日期", ""))[:10]
        else:
            px = rd(code, "px")
            if px is not None and len(px):
                px = px.copy()
                px["close"] = pd.to_numeric(px["close"], errors="coerce")
                px["outstanding_share"] = pd.to_numeric(px.get("outstanding_share"), errors="coerce")
                last = px.dropna(subset=["close"]).iloc[-1]
                rec["最新收盘"] = float(last["close"])
                rec["流通市值亿元"] = float(last["close"]) * float(
                    last.get("outstanding_share", np.nan) or np.nan) / 1e8

        # --- 财务摘要（新浪）：年报 2023---2025 + 半年报 2025H1 / 2026H1
        #     第二部分统一以 2026 年半年报为财务口径，年报数据保留作趋势对照
        fa = rd(code, "fin_abstract")
        fi = rd(code, "fin_ind")
        periods = [(yr, f"{yr}1231") for yr in ANNUAL] + \
                  [("2025H1", H1_PREV), ("2026H1", H1)]
        if fa is not None and len(fa):
            fa = fa.copy()
            fa["指标"] = fa["指标"].astype(str).str.strip()
            fa["选项"] = fa["选项"].astype(str).str.strip()
            common = fa[fa["选项"] == "常用指标"]
            for metric, key in FA_METRICS:
                s = common[common["指标"] == metric]
                if not len(s):
                    continue
                s = s.iloc[0]
                for label, col in periods:
                    if col in s.index:
                        rec[f"{key}{label}"] = num(s[col])
            # 净资产为负时接口不返回 ROE，用财务指标表的披露值兜底
            if not np.isfinite(rec.get("ROE2026H1", np.nan)):
                v = fin_ind_at(fi, "净资产收益率(%)", "2026-06-30")
                if np.isfinite(v):
                    rec["ROE2026H1"] = v
            # 单位换算：营收/净利 -> 亿元
            for key in ("营业收入", "归母净利润"):
                for label, _ in periods:
                    c = f"{key}{label}"
                    if c in rec and np.isfinite(rec.get(c, np.nan)):
                        rec[f"{c}(亿元)"] = rec[c] / 1e8
            if np.isfinite(rec.get("营业收入2025", np.nan)) and \
               np.isfinite(rec.get("营业收入2023", np.nan)) and rec["营业收入2023"] > 0:
                rec["营收两年CAGR%"] = ((rec["营业收入2025"] / rec["营业收入2023"]) ** 0.5 - 1) * 100
            if np.isfinite(rec.get("营业收入2026H1", np.nan)) and \
               np.isfinite(rec.get("营业收入2025H1", np.nan)) and rec["营业收入2025H1"] > 0:
                rec["营收同比2026H1%"] = (rec["营业收入2026H1"] / rec["营业收入2025H1"] - 1) * 100
            if np.isfinite(rec.get("归母净利润2025", np.nan)):
                rec["2025盈亏"] = "盈利" if rec["归母净利润2025"] > 0 else "亏损"
            if np.isfinite(rec.get("归母净利润2026H1", np.nan)):
                rec["2026H1盈亏"] = "盈利" if rec["归母净利润2026H1"] > 0 else "亏损"

        # --- 总股本与股本变动（巨潮）
        sc = rd(code, "share_chg")
        if sc is not None and len(sc):
            sc = sc.copy()
            sc["变动日期"] = pd.to_datetime(sc["变动日期"], errors="coerce")
            sc["总股本"] = pd.to_numeric(sc.get("总股本"), errors="coerce")
            sc = sc.dropna(subset=["变动日期"]).sort_values("变动日期")
            if len(sc):
                last = sc.iloc[-1]
                rec["总股本亿股"] = float(last["总股本"]) / 1e4 if np.isfinite(
                    float(last["总股本"] or np.nan)) else np.nan
                rec["最近股本变动日"] = str(last["变动日期"])[:10]
                rec["股本变动次数"] = int(len(sc[sc["变动日期"] >= pd.Timestamp("2023-01-01")]))
                reasons = sc[sc["变动日期"] >= pd.Timestamp("2023-01-01")]["变动原因"].dropna()
                rec["近三年股本变动原因"] = "；".join(
                    sorted(set(str(x) for x in reasons)))[:70]

        # --- 分红（巨潮）
        fh = rd(code, "fhps")
        if fh is not None and len(fh):
            fh = fh.copy()
            dcol = next((c for c in ("报告期", "方案公告日", "股权登记日", "除权除息日",
                                     "最新公告日期") if c in fh.columns), None)
            if dcol is None:
                rec["近三年分红次数"] = 0
                rec["近三年每股分红合计"] = 0.0
            else:
                fh[dcol] = pd.to_datetime(fh[dcol], errors="coerce")
                pcol = next((c for c in ("现金分红-现金分红比例", "派息比例",
                                         "现金分红比例") if c in fh.columns), None)
                if pcol:
                    fh[pcol] = pd.to_numeric(fh[pcol], errors="coerce")
                prog = fh.get("方案进度", pd.Series("", index=fh.index)).astype(str)
                impl = fh[(fh[dcol] >= pd.Timestamp("2022-01-01")) &
                          (prog.str.contains("实施", na=False) | ~prog.str.contains("预案|取消", na=False))]
                rec["近三年分红次数"] = int(len(impl))
                # 现金分红比例为「每 10 股派现（元）」，换算为每股须除以 10
                rec["近三年每股分红合计"] = float(fh.loc[impl.index, pcol].sum()) / 10.0 \
                    if (pcol and len(impl)) else 0.0
                rec["最近分红方案"] = str(prog.iloc[-1])[:20]

        # --- 公告事件（巨潮，近三年）
        dc = rd(code, "disc")
        rec["名称"] = name  # 事件表用同一公司名：注意不要被下面的循环变量覆盖
        ev = {cat: 0 for cat, _ in EVENT_RULES}
        if dc is not None and len(dc):
            dc = dc.copy()
            dc["公告时间"] = pd.to_datetime(dc["公告时间"], errors="coerce")
            dc = dc[dc["公告时间"] >= pd.Timestamp("2023-09-01")]
            for t in dc["公告标题"].astype(str):
                for cat in classify(t):
                    ev[cat] += 1
            rec["近三年公告数"] = int(len(dc))
            # 记录最相关的三条“转型/融资”类公告标题，供人工核对
            key = dc[dc["公告标题"].astype(str).str.contains(
                r"向特定对象发行|重大资产重组|收购|战略合作|框架协议", na=False)]
            rec["关键公告示例"] = " ｜ ".join(
                key["公告标题"].astype(str).head(3).tolist())[:150]
        rec.update({f"公告-{k}": v for k, v in ev.items()})
        rows.append(rec)
        erows.append({"代码": code, "名称": rec.get("名称", name), **ev,
                      "近三年公告数": rec.get("近三年公告数", 0)})

    m = pd.DataFrame(rows)
    # 三级行业缺失（申万“农业综合Ⅱ”无三级行业）时回退到二级行业
    m["三级行业"] = m["三级行业"].fillna("").replace("", np.nan)
    m["二级行业"] = m["二级行业"].fillna("").replace("", np.nan)
    m["三级行业"] = m["三级行业"].fillna(m["二级行业"]).fillna("未分类")
    e = pd.DataFrame(erows)
    m.to_csv(os.path.join(CLEAN, "company_master.csv"), index=False, encoding="utf-8-sig")
    e.to_csv(os.path.join(CLEAN, "company_events.csv"), index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------ 行业汇总
    ind = m.groupby("三级行业").agg(
        公司数=("代码", "count"),
        总流通市值亿元=("流通市值亿元", "sum"),
        平均营收2026H1亿元=("营业收入2026H1(亿元)", "mean"),
        营收同比中位数=("营收同比2026H1%", "median"),
        亏损公司数=("2026H1盈亏", lambda s: int((s == "亏损").sum())),
        平均ROE2026H1=("ROE2026H1", "mean"),
        平均资产负债率2026H1=("资产负债率2026H1", "mean"),
    ).reset_index().sort_values("公司数", ascending=False)
    ind.round(2).to_csv(os.path.join(CLEAN, "company_by_industry.csv"),
                        index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------ tikz 数据
    d = ind[ind["公司数"] > 0].sort_values("公司数", ascending=False)
    with open(os.path.join(CLEAN, "comp_ind_count.dat"), "w", encoding="utf-8") as fh:
        fh.write("i n label\n")
        for i, (_, r) in enumerate(d.iterrows()):
            fh.write(f"{i} {int(r['公司数'])} {r['三级行业']}\n")

    mc = pd.to_numeric(m["流通市值亿元"], errors="coerce").dropna()
    if len(mc):
        bins = [0, 20, 50, 100, 200, 500, 1000, 1e9]
        labels = ["<20", "20-50", "50-100", "100-200", "200-500", "500-1000", ">1000"]
        cnt = pd.cut(mc, bins=bins, labels=labels).value_counts().reindex(labels).fillna(0)
        with open(os.path.join(CLEAN, "comp_mktcap.dat"), "w", encoding="utf-8") as fh:
            fh.write("i n label\n")
            for i, (lb, n) in enumerate(cnt.items()):
                fh.write(f"{i} {int(n)} {lb}\n")

    roe = pd.to_numeric(m["ROE2026H1"], errors="coerce").dropna()
    if len(roe):
        # 半年度 ROE（未年化），分档按半年口径设置
        bins = [-100, -10, -5, -2, 0, 2, 5, 10, 100]
        labels = ["<-10", "-10~-5", "-5~-2", "-2~0", "0~2", "2~5", "5~10", ">10"]
        cnt = pd.cut(roe, bins=bins, labels=labels).value_counts().reindex(labels).fillna(0)
        with open(os.path.join(CLEAN, "comp_roe.dat"), "w", encoding="utf-8") as fh:
            fh.write("i n label\n")
            for i, (lb, n) in enumerate(cnt.items()):
                fh.write(f"{i} {int(n)} {lb}\n")

    sc = m[["代码", "营收同比2026H1%", "销售净利率2026H1", "流通市值亿元", "三级行业"]].copy()
    sc = sc.dropna(subset=["营收同比2026H1%", "销售净利率2026H1"])
    sc = sc[(sc["营收同比2026H1%"].between(-60, 120)) &
            (sc["销售净利率2026H1"].between(-80, 40))]
    with open(os.path.join(CLEAN, "comp_growth_scatter.dat"), "w", encoding="utf-8") as fh:
        fh.write("growth margin cap label\n")
        for _, r in sc.iterrows():
            fh.write(f"{r['营收同比2026H1%']:.2f} {r['销售净利率2026H1']:.2f} "
                     f"{r['流通市值亿元']:.1f} {r['代码']}\n")

    # 资产负债率 - ROE 散点（融资需求分层的依据；2026 年 6 月末 / 2026 年半年报）
    dd = m[["代码", "资产负债率2026H1", "ROE2026H1", "归母净利润2026H1(亿元)"]].copy()
    dd = dd.dropna(subset=["资产负债率2026H1", "ROE2026H1"])
    with open(os.path.join(CLEAN, "comp_debt_roe.dat"), "w", encoding="utf-8") as fh:
        fh.write("debt roe np label\n")
        for _, r in dd.iterrows():
            fh.write(f"{r['资产负债率2026H1']:.2f} {r['ROE2026H1']:.2f} "
                     f"{r['归母净利润2026H1(亿元)']:.2f} {r['代码']}\n")

    # 高负债 + 亏损公司（融资需求最高的一档；2026 年半年报口径）
    de = pd.to_numeric(m["资产负债率2026H1"], errors="coerce")
    npf = pd.to_numeric(m["归母净利润2026H1(亿元)"], errors="coerce")
    risk = m[(npf < 0) & (de > 65)].copy()
    risk["de"] = de[risk.index]
    risk = risk.sort_values("de", ascending=False)
    with open(os.path.join(CLEAN, "comp_risk.dat"), "w", encoding="utf-8") as fh:
        fh.write("i debt label\n")
        for i, (_, r) in enumerate(risk.iterrows()):
            fh.write(f"{i} {r['de']:.1f} {r['名称']}\n")

    # ------------------------------------------------------------ LaTeX 表
    write_tex(m, ind)
    write_industry_tables(m)

    # ------------------------------------------------------------ 汇总说明
    log("\n## 汇总统计\n")
    log(f"- 公司数量：{len(m)}")
    log(f"- 有市值数据：{int(mc.count()) if len(mc) else 0}")
    if len(mc):
        log(f"- 流通市值（亿元）：合计 {mc.sum():.0f}，中位数 {mc.median():.1f}，"
            f"最大 {mc.max():.0f}")
    if "2026H1盈亏" in m:
        log(f"- 2026 年上半年亏损公司：{int((m['2026H1盈亏'] == '亏损').sum())} 家")
    if "2025盈亏" in m:
        log(f"- 2025 年亏损公司（对照）：{int((m['2025盈亏'] == '亏损').sum())} 家")
    if "ROE2026H1" in m:
        r2 = pd.to_numeric(m["ROE2026H1"], errors="coerce")
        log(f"- 2026 年上半年 ROE（未年化）：中位数 {r2.median():.2f}%，"
            f"为正的公司 {int((r2 > 0).sum())} 家，为负 {int((r2 < 0).sum())} 家")
    log("\n### 按三级行业的公司数与规模\n")
    log(ind.to_string(index=False))
    log("\n### 公告事件计数（近三年，全部公司合计）\n")
    tot = e[[c for c in e.columns if c not in ("代码", "名称")]].sum()
    log(tot.to_string())
    with open(os.path.join(NOTES, "company_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + "\n")
    log(f"\n→ {CLEAN}/company_master.csv, {CLEAN}/company_by_industry.csv, "
        f"notes/company_summary.md")


def industry_groups() -> dict[str, list[str]]:
    """章节 -> 申万三级行业列表（用于分章生成公司表）。"""
    return {
        "planting": ["种子", "粮食种植", "其他种植业", "食用菌"],
        "breeding": ["生猪养殖", "肉鸡养殖", "其他养殖"],
        "feed": ["畜禽饲料", "水产饲料"],
        "vet": ["动物保健Ⅲ", "动物保健"],
        "processing": ["粮油加工", "果蔬加工", "其他农产品加工"],
        "fishery": ["水产养殖", "海洋捕捞", "林业Ⅲ", "宠物食品"],
        "misc": ["农业综合Ⅱ"],
    }


def write_industry_tables(m: pd.DataFrame) -> None:
    os.makedirs(GEN, exist_ok=True)
    cols = [("代码", "代码", None), ("名称", "公司简称", None),
            ("流通市值亿元", "市值（亿元）", 1),
            ("营业收入2026H1(亿元)", "营收（亿元）", 1),
            ("营收同比2026H1%", "同比（\\%）", 1),
            ("归母净利润2026H1(亿元)", "净利（亿元）", 2),
            ("ROE2026H1", "ROE（\\%）", 1),
            ("公告-再融资", "再融资公告", 0),
            ("公告-重大重组与并购", "重组公告", 0)]
    for key, inds in industry_groups().items():
        sub = m[m["三级行业"].isin(inds)].copy()
        if not sub.empty:
            sub = sub.sort_values("流通市值亿元", ascending=False, na_position="last")
        out = [r"\begingroup\scriptsize\setlength{\tabcolsep}{2pt}",
               r"\begin{longtable}{@{}llrrrrrrr@{}}",
               r"\caption{农业上市公司分行业明细（%s；财务为 2026 年半年报，ROE 未年化，公告计数窗口 2023-09---2026-09）}\label{tab:comp-%s}\\" % (
                   "、".join(inds), key),
               r"\toprule", " & ".join(c[1] for c in cols) + r" \\", r"\midrule",
               r"\endfirsthead",
               r"\multicolumn{9}{l}{\small（续）}\\", r"\toprule",
               " & ".join(c[1] for c in cols) + r" \\", r"\midrule", r"\endhead",
               r"\bottomrule", r"\endlastfoot"]
        for _, r in sub.iterrows():
            out.append(" & ".join(
                tex_escape(r.get(k, "")) if nd is None else fmt(r.get(k, np.nan), nd)
                for k, _, nd in cols) + r" \\")
        out += [r"\end{longtable}",
                r"\endgroup"]
        with open(os.path.join(GEN, f"comp_{key}.tex"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")


def tex_escape(s: str) -> str:
    s = str(s or "")
    for a, b in [("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"),
                 ("$", r"\$"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}")]:
        s = s.replace(a, b)
    return s


def fmt(v, nd: int = 1, dash: str = "—") -> str:
    try:
        f = float(v)
        if not np.isfinite(f):
            return dash
        return f"{f:,.{nd}f}"
    except (TypeError, ValueError):
        return dash


def write_tex(m: pd.DataFrame, ind: pd.DataFrame) -> None:
    os.makedirs(GEN, exist_ok=True)
    # 全量公司表（longtable，横向滚动风险大 -> 精简列）
    m2 = m.copy()
    m2["行业"] = m2["三级行业"].fillna("")
    cols = [("代码", "代码", None), ("名称", "公司简称", None),
            ("行业", "申万三级行业", None),
            ("流通市值亿元", "市值（亿元）", 1),
            ("营业收入2026H1(亿元)", "营收（亿元）", 1),
            ("营收同比2026H1%", "同比（\\%）", 1),
            ("归母净利润2026H1(亿元)", "净利（亿元）", 2),
            ("ROE2026H1", "ROE（\\%）", 1),
            ("资产负债率2026H1", "负债率（\\%）", 1)]
    m2 = m2.sort_values("流通市值亿元", ascending=False, na_position="last")
    out = [r"\begingroup\scriptsize\setlength{\tabcolsep}{1.5pt}",
           r"\begin{longtable}{@{}llp{1.9cm}rrrrrr@{}}",
           r"\caption{申万农林牧渔行业 A 股上市公司画像总表（按流通市值降序；市值时点 2026-09-24，"
           r"财务为 2026 年半年报（未年化），资产负债率为 2026 年 6 月末）}"
           r"\label{tab:company-master}\\", r"\toprule",
           " & ".join(c[1] for c in cols) + r" \\", r"\midrule", r"\endfirsthead",
           r"\multicolumn{9}{l}{\small（续）}\\", r"\toprule",
           " & ".join(c[1] for c in cols) + r" \\", r"\midrule", r"\endhead",
           r"\bottomrule", r"\endlastfoot"]
    for _, r in m2.iterrows():
        cells = []
        for key, _, nd in cols:
            v = r.get(key, "")
            if nd is None:
                cells.append(tex_escape(v))
            else:
                cells.append(fmt(v, nd))
        out.append(" & ".join(cells) + r" \\")
    out += [r"\end{longtable}",
            r"\endgroup"]
    with open(os.path.join(GEN, "company_master.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    # 分行业汇总表
    i2 = ind.rename(columns={"三级行业": "行业"})
    out = [r"\begin{table}[htbp]\centering\footnotesize",
           r"\caption{按申万三级行业汇总的农业上市公司数量与经营指标（2026 年半年报口径；"
           r"ROE 为半年报披露的算术平均值、未年化，市值时点 2026-09-24）}",
           r"\label{tab:company-by-industry}",
           r"\begin{tabular}{@{}lrrrrrr@{}}", r"\toprule",
           r"申万三级行业 & 公司数 & 总流通市值 & 平均营收 & 营收同比 & 亏损 & 平均 ROE \\",
           r" & & （亿元） & 2026H1（亿元） & 中位数（\%） & 公司数 & 2026H1（\%） \\", r"\midrule"]
    for _, r in i2.iterrows():
        out.append(f"{tex_escape(r['行业'])} & {int(r['公司数'])} & "
                   f"{fmt(r['总流通市值亿元'], 0)} & {fmt(r['平均营收2026H1亿元'], 1)} & "
                   f"{fmt(r['营收同比中位数'], 1)} & {int(r['亏损公司数'])} & "
                   f"{fmt(r['平均ROE2026H1'], 1)} \\\\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\end{table}"]
    with open(os.path.join(GEN, "company_by_ind.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    build()
