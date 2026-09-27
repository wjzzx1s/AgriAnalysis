#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 data/clean 的分析结果表生成为 LaTeX 表格片段（tex/gen/*.tex）。

正文用 \\input{tex/gen/xxx.tex} 引用，保证正文数字与数据完全一致、
且不出现手工誊抄误差。所有表都是 booktabs + threeparttable 风格，
表下附数据来源（\\srcfile）与口径说明。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agri_meta import SW_L2, SW_L3  # noqa: E402
from common import CLEAN, ROOT  # noqa: E402

GEN = os.path.join(ROOT, "tex", "gen")
os.makedirs(GEN, exist_ok=True)

CN = str.maketrans("0123456789.%+-", "0123456789.%+-")


def fmt(v, nd: int = 2, plus: bool = False) -> str:
    """数值 → LaTeX 文本（千分位用 \\, 分隔，缺失写 --- ）。"""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return r"\nodata"
    if isinstance(v, str):
        return v
    if isinstance(v, (int, np.integer)):
        return f"{v:,}".replace(",", r"\,")
    if isinstance(v, (float, np.floating)):
        s = f"{v:,.{nd}f}".replace(",", r"\,")
        if plus and v > 0:
            s = "+" + s
        return s
    return str(v)


def esc(s) -> str:
    """转义 LaTeX 特殊字符。"""
    s = str(s)
    for a, b in [("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#"),
                 ("$", r"\$"), ("{", r"\{"), ("}", r"\}")]:
        s = s.replace(a, b)
    return s


def table(rows: list[dict], caption: str, label: str, colspec: str,
          headers: list[str] | None = None, note: str = "", src: str = "",
          size: str = r"\small", longtable: bool = False,
          align_map: dict | None = None, nd: int = 2,
          nd_map: dict | None = None) -> str:
    """rows: [{列名: 值}]；headers 为中文表头（与 rows 的键一一对应）。
    nd_map 可按列覆盖小数位（如整数的滞后阶用 0）。"""
    df = pd.DataFrame(rows)
    cols = list(df.columns)
    heads = headers or cols
    align_map = align_map or {}
    nd_map = nd_map or {}
    out = []
    env = "longtable" if longtable else "table"
    if not longtable:
        out.append(r"\begin{table}[htbp]")
        out.append(r"\centering")
    else:
        out.append(r"\begin{longtable}{" + colspec + "}")
    out.append(size)
    if not longtable:
        # 表格题注统一置于表格上方（与“表 X-N”编号约定一致）
        out.append(r"\caption{" + caption + "}")
        out.append(r"\label{" + label + "}")
        # 只在超出版心时缩放：\resizebox{\textwidth}{!} 会把窄表放大，
        # 导致表格文字大于正文（用户要求表格字号不超过正文）。
        out.append(r"\begin{adjustbox}{max width=\textwidth}")
        out.append(r"\begin{tabular}{" + colspec + "}")
    out.append(r"\toprule")
    out.append(" & ".join(heads) + r" \\")
    out.append(r"\midrule")
    if longtable:
        out.append(r"\endfirsthead")
        out.append(r"\toprule")
        out.append(" & ".join(heads) + r" \\")
        out.append(r"\midrule")
        out.append(r"\endhead")
        out.append(r"\bottomrule")
        out.append(r"\endlastfoot")
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (int, np.integer, float, np.floating)) and not isinstance(v, bool):
                cells.append(fmt(v, nd=nd_map.get(c, nd), plus=align_map.get(c) == "plus"))
            else:
                cells.append(esc(v))
        out.append(" & ".join(cells) + r" \\")
    out.append(r"\bottomrule")
    if longtable:
        out.append(r"\end{longtable}")
    else:
        out.append(r"\end{tabular}")
        out.append(r"\end{adjustbox}")
    if longtable:
        # longtable 的题注写在表体内（表头之后），故后接 LaTeX 换行
        out.append("\\caption{" + caption + "}\\label{" + label + "}\\\\")
    # 用户要求：删除图表下的“资料来源”一行。口径文本仍保留在脚本里备查，但不写入 tex。
    if note:
        out.append(r"\par\vspace{2pt}{\footnotesize\sffamily " + note + r"}")
    if not longtable:
        out.append(r"\end{table}")
    return "\n".join(out) + "\n"


def load(name: str, index_col=None) -> pd.DataFrame | None:
    p = os.path.join(CLEAN, f"{name}.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, encoding="utf-8-sig", index_col=index_col)


def write(name: str, text: str) -> None:
    with open(os.path.join(GEN, f"{name}.tex"), "w", encoding="utf-8") as fh:
        fh.write("% 由 scripts/make_tables.py 自动生成，请勿手工编辑\n" + text)
    print(f"  -> tex/gen/{name}.tex")


# ---------------------------------------------------------------- 各表
def t_fut_summary() -> None:
    df = load("fut_summary")
    if df is None:
        return
    order = ["养殖", "粮食", "油料", "压榨链", "软商品", "林果", "其他"]
    df["_o"] = df["大类"].map({k: i for i, k in enumerate(order)}).fillna(99)
    df = df.sort_values(["_o", "代码"]).drop(columns=["_o"])
    keep = ["品种", "代码", "大类", "起始", "结束", "月度数", "均价", "最新",
            "区间涨跌%", "年化波动%", "历史最高", "历史最低", "峰谷比"]
    rows = df[keep].to_dict("records")
    write("fut_summary", table(
        rows, caption="农产品相关期货品种样本概况（主力连续，全部可得历史；末月 2026 年 9 月为不完整月度）",
        label="tab:fut-summary",
        colspec=r"@{}lllllrrrrrrrr@{}",
        headers=["品种", "代码", "大类", "起始", "结束", "月度数", "月均价格",
                 "最新", "区间涨跌\\%", "年化波动\\%", "历史最高", "历史最低", "峰谷比"],
        align_map={"区间涨跌%": "plus"},
        size=r"\scriptsize",
        src=r"期货主力连续合约行情；"
            r"价格单位见附录 \ref{app:contracts}，区间涨跌幅为首末月度均价之比减一；"
            r"末月为 2026 年 9 月的不完整月度（行情截至 2026-09-24）。"))


def t_hog_legs() -> None:
    for src_name, out, cap, lab in [
        ("hog_legs_long", "hog_legs_long", "生猪现货价格指数的周期分段（2015 年 1 月---2026 年 4 月（末段截至 4 月）；ZigZag 阈值 20\\%）",
         "tab:hog-legs-long"),
        ("hog_legs", "hog_legs_fut", "生猪期货价格（2021 年上市至今）的周期分段（末段截至 2026 年 4 月；ZigZag 阈值 18\\%）",
         "tab:hog-legs-fut"),
    ]:
        df = load(src_name)
        if df is None:
            continue
        keep = [c for c in ["起点", "终点", "起点价", "终点价", "方向", "月数", "幅度%"]
                if c in df.columns]
        rows = df[keep].to_dict("records")
        write(out, table(
            rows, caption=cap, label=lab,
            colspec=r"@{}llrrlrr@{}",
            headers=["起点", "终点", "起点价", "终点价", "方向", "持续月数", "幅度\\%"],
            align_map={"幅度%": "plus"},
            src=r"猪易数据生猪价格指数与生猪期货主力连续合约行情，"
                r"分段用 ZigZag 算法（" +
                ("波动幅度阈值 20\\%" if src_name == "hog_legs_long" else "波动幅度阈值 18\\%") +
                r"）。"))


def t_hog_capacity() -> None:
    cap = load("hog_capacity_recent")
    if cap is None or cap.empty:
        return
    names = {"周期": "期间", "能繁母猪存栏": "能繁母猪（万头）",
             "猪肉产量": "猪肉产量（万吨）", "生猪存栏": "生猪存栏（万头）",
             "生猪出栏": "生猪出栏（万头）"}
    cap2 = cap.rename(columns=names)
    rows = cap2.to_dict("records")
    write("hog_capacity_recent", table(
        rows, caption="能繁母猪存栏与生猪产销：2025 年季度/月度与 2026 年最新数据",
        label="tab:hog-capacity-recent",
        colspec=r"@{}lrrrr@{}",
        headers=list(cap2.columns),
        nd=0, size=r"\footnotesize",
        src=r"国家统计局与农业农村部公开数据；"
            r"2025 年季度/月度为国家统计局统计口径，"
            r"2025 年（全年/年末）与 2026 年数据来自国家统计局年度数据与"
            r"农业农村部公开发布（来源逐行记录于 "
            r"\texttt{data/raw/hog\_capacity\_official.csv}）；"
            r"— 表示该口径当期未公布。"))


def dat_fut_norm(codes: list[str] | None = None,
                 start: str = "2021-02-01", out: str = "fut_norm_grain.dat") -> None:
    """多品种归一化价格（2021-02 = 100），供 pgfplots 多列折线图。"""
    if codes is None:
        codes = ["LH", "JD", "C", "M", "Y", "P", "SR", "CF", "RU", "AP", "CJ", "RM"]
    series = {}
    for sym in codes:
        p = os.path.join(CLEAN, f"fut_m_{sym}.dat")
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p, sep=r"\s+", comment="#", header=None,
                        names=["x", "y"], engine="python")
        x0 = int(start[:4]) + (int(start[5:7]) - 1) / 12
        d = d[d["x"] >= x0 - 1e-9].reset_index(drop=True)
        if len(d) < 20:
            continue
        series[sym] = pd.Series((d["y"] / d["y"].iloc[0] * 100).round(2).values,
                                index=d["x"].round(4))
    if not series:
        return
    tbl = pd.DataFrame(series).sort_index()
    tbl.index.name = "x"
    tbl.to_csv(os.path.join(CLEAN, out), sep=" ", na_rep="nan",
               float_format="%.2f")


def dat_vol() -> None:
    """主窗口年化波动率（供条形图）。"""
    df = load("vol_summary")
    if df is None or df.empty:
        return
    df = df.sort_values("主窗口年化波动%", ascending=False)
    with open(os.path.join(CLEAN, "vol_bar.dat"), "w", encoding="utf-8") as fh:
        fh.write("i vol label full\n")
        for i, (_, r) in enumerate(df.iterrows()):
            fh.write(f"{i} {r['主窗口年化波动%']:.2f} {r['代码']} "
                     f"{r['全样本年化波动%']:.2f}\n")


def dat_phase_scatter() -> None:
    """阶段收益散点（上涨段月均收益 vs 下跌段月均收益），供 pgfplots 散点图使用。"""
    df = load("cycle_phase_futures")
    if df is None or df.empty:
        return
    df = df[df["代码"] != "LH"]
    with open(os.path.join(CLEAN, "phase_scatter.dat"), "w", encoding="utf-8") as fh:
        fh.write("up down label\n")
        for _, r in df.iterrows():
            fh.write(f"{r['上涨段月均收益%']:.3f} {r['下跌段月均收益%']:.3f} {r['代码']}\n")
    with open(os.path.join(CLEAN, "phase_scatter_labels.dat"), "w", encoding="utf-8") as fh:
        fh.write("# code name\n")
        for _, r in df.iterrows():
            fh.write(f"{r['代码']} {r['品种']}\n")


def dat_sw_corr() -> None:
    """申万子行业指数与生猪期货的相关性（供条形图）。

    标签带上申万层级（一/二/三级）：同一名称在不同层级会出现两次
    （如二级“动物保健”与三级“动物保健Ⅲ”），只写名称无法区分。
    """
    df = load("sw_corr_hog")
    if df is None or df.empty:
        return
    df = df.sort_values("与生猪期货月收益相关", ascending=False)
    with open(os.path.join(CLEAN, "sw_corr_hog.dat"), "w", encoding="utf-8") as fh:
        fh.write("i rho label\n")
        for i, (_, r) in enumerate(df.iterrows()):
            lv = str(r.get("层级", "")).strip()
            label = f"{r['行业名称']}（{lv}）" if lv else str(r["行业名称"])
            fh.write(f"{i} {r['与生猪期货月收益相关']:.4f} {label}\n")


def dat_phase_bar(kind: str, name: str) -> None:
    """阶段同向占比条形图数据。"""
    df = load(f"cycle_phase_{kind}")
    if df is None or df.empty:
        return
    df = df[df["与猪价同向月占比%"].notna()].sort_values("与猪价同向月占比%", ascending=False)
    with open(os.path.join(CLEAN, name), "w", encoding="utf-8") as fh:
        fh.write("i pct label\n")
        for i, (_, r) in enumerate(df.iterrows()):
            code = r.get("代码") or r.get("行业代码")
            fh.write(f"{i} {float(r['与猪价同向月占比%']):.2f} {code}\n")


def t_corr_group() -> None:
    """按大类汇总同期（2021-02～2026-08）月度收益率相关矩阵。"""
    df = load("corr_m_short", index_col=0)
    if df is None or df.empty:
        return
    from agri_meta import FUT_META
    codes = [c for c in df.columns if c in FUT_META]
    df = df.loc[codes, codes]
    pairs = []
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            v = df.loc[a, b]
            if pd.notna(v):
                pairs.append({"大类A": FUT_META[a][1], "大类B": FUT_META[b][1],
                              "r": float(v)})
    p = pd.DataFrame(pairs)
    g = (p.groupby(["大类A", "大类B"])["r"]
         .agg(组合数="count", 平均相关="mean", 最大相关="max", 最小相关="min")
         .reset_index())
    g["类别对"] = g["大类A"] + " -- " + g["大类B"]
    g = g.sort_values("平均相关", ascending=False)
    rows = g[["类别对", "组合数", "平均相关", "最大相关", "最小相关"]].round(3).to_dict("records")
    write("corr_group", table(
        rows, caption="同一时间窗口（2021-02～2026-08）内大类之间的平均相关系数",
        label="tab:corr-group", colspec=r"@{}lrrrr@{}",
        headers=["类别对", "品种对数", "平均相关", "最大相关", "最小相关"],
        nd=3,
        src=r"22 个品种的月度对数收益率在同一 67 个月窗口内的相关系数，"
            r"5\% 显著性阈值 $|\rho|>0.24$。"))


def t_corr_hog() -> None:
    df = load("corr_m_short", index_col=0)
    if df is None or df.empty or "LH" not in df.columns:
        return
    from agri_meta import FUT_META
    s = df["LH"].dropna().drop("LH").sort_values(ascending=False)
    rows = [{"品种": FUT_META[k][0] if k in FUT_META else k,
             "大类": FUT_META[k][1] if k in FUT_META else "",
             "相关系数": v} for k, v in s.items() if k != "LH"]
    rows = sorted(rows, key=lambda r: -abs(r["相关系数"]))
    write("corr_hog", table(
        rows, caption="各品种与生猪期货月度收益率的相关系数（2021-02～2026-08）",
        label="tab:corr-hog", colspec=r"@{}llr@{}",
        headers=["品种", "大类", "与生猪期货的相关系数"],
        align_map={"相关系数": "plus"}, nd=3,
        src=r"样本 67 个月，5\% 显著性阈值 $|\rho|>0.24$。"))


def t_leadlag() -> None:
    df = load("leadlag2_summary")
    if df is None:
        return
    rows = df.to_dict("records")
    write("leadlag", table(
        rows, caption="以生猪周期分量为基准的领先滞后关系（月度，±12 个月）",
        label="tab:leadlag", colspec=r"@{}lllrrrl@{}",
        headers=["品种", "代码", "大类", "同期相关", "最大显著相关", "滞后月", "判定"],
        align_map={"同期相关": "plus", "最大显著相关": "plus"}, nd=3,
        nd_map={"滞后月": 0},
        src=r"比较对象为价格对 12 个月移动平均的偏离（周期分量），样本 2021-02～2026-08，"
            r"滞后阶 $k\in[-9,+9]$（每阶要求有效样本不少于 48 个月）；"
            r"只报告通过 5\% 显著性的滞后阶；滞后月 $k>0$ 表示生猪领先 $k$ 个月。"))


def t_transmission() -> None:
    df = load("transmission_summary")
    if df is None:
        return
    rows = df.to_dict("records")
    write("transmission", table(
        rows, caption="生猪价格向各品种的传导回归（月度收益，HAC 稳健标准误；“显著”指 $|t|>1.96$，即 5\\% 水平）",
        label="tab:transmission", colspec=r"@{}lllrrrrl@{}",
        headers=["品种", "代码", "大类", "显著滞后阶数", "最优滞后 $k$", "$\\beta$",
                 "$t$ 值", "显著 $k$ 清单"],
        align_map={"β": "plus"}, nd=3,
        nd_map={"显著滞后阶": 0, "最优滞后k(月)": 0},
        src=r"$r^{i}_t=\alpha+\beta_k r^{\text{LH}}_{t-k}+\varepsilon_t$，"
            r"Newey--West 滞后阶 6，样本 2021-02～2026-08。"))


def t_phase() -> None:
    for src_name, out, cap, lab, extra in [
        ("cycle_phase_long", "phase_long",
         "生猪现货价格上涨段与下跌段中各品种的月均收益（2015—2026）",
         "tab:phase-long", ""),
        ("cycle_phase_futures", "phase_futures",
         "生猪期货上涨段与下跌段中各品种的月均收益（2021—2026）",
         "tab:phase-futures", ""),
    ]:
        df = load(src_name)
        if df is None:
            continue
        rows = df.to_dict("records")
        cols = list(df.columns)
        heads = {"品种": "品种", "代码": "代码", "大类": "大类",
                 "上涨段月均收益%": "上涨段月均\\%", "下跌段月均收益%": "下跌段月均\\%",
                 "差值(pp)": "差值（pp）", "同向月占比%": "同向月占比\\%",
                 "上涨段月均%": "上涨段月均\\%", "下跌段月均%": "下跌段月均\\%",
                 "差值pp": "差值（pp）", "上涨月数": "上涨月数", "下跌月数": "下跌月数",
                 "与猪价同向月占比%": "同向月占比\\%"}
        write(out, table(
            rows, caption=cap, label=lab,
            colspec=r"@{}lll" + "r" * (len(cols) - 3) + r"@{}",
            headers=[heads.get(c, c) for c in cols],
            align_map={"差值(pp)": "plus", "差值pp": "plus",
                       "上涨段月均收益%": "plus", "上涨段月均%": "plus",
                       "下跌段月均收益%": "plus", "下跌段月均%": "plus"},
            nd=2, size=r"\scriptsize",
            src=r"“同向月占比”指该品种月度收益与生猪价格同号的月份比例。"))


def t_phase_sw() -> None:
    df = load("cycle_phase_sw")
    if df is None:
        return
    rows = df.to_dict("records")
    write("phase_sw", table(
        rows, caption="申万农业子行业指数在生猪上涨段与下跌段的月均收益（2021—2026）",
        label="tab:phase-sw", colspec=r"@{}lllr rr@{}".replace(" ", ""),
        headers=["行业代码", "行业名称", "层级", "上涨段月均\\%", "下跌段月均\\%",
                 "差值（pp）"],
        align_map={"上涨段月均收益%": "plus", "下跌段月均收益%": "plus",
                   "差值(pp)": "plus"},
        size=r"\scriptsize",
        src=r"申万行业指数月度收盘。"))


def t_sw_summary() -> None:
    df = load("sw_summary")
    if df is None:
        return
    nm = {**SW_L2, **SW_L3}
    codes = df["行业代码"].astype(str)
    df["层级"] = np.where(codes.isin(SW_L2), "二级",
                          np.where(codes.isin(SW_L3), "三级", "一级"))
    rows = df[["行业代码", "行业名称", "层级", "起始", "最新", "近1年涨跌%",
               "近3年涨跌%", "历史最高", "历史最低", "峰谷比"]].to_dict("records")
    write("sw_summary", table(
        rows, caption="申万农业行业指数概况（截至 2026 年 9 月）",
        label="tab:sw-summary", colspec=r"@{}lllrrrrrrr @{}".replace(" ", ""),
        headers=["行业代码", "行业名称", "层级", "起始", "最新", "近 1 年\\%",
                 "2023 年初以来\\%", "历史最高", "历史最低", "峰谷比"],
        align_map={"近1年涨跌%": "plus", "近3年涨跌%": "plus"},
        size=r"\scriptsize",
        src=r"申万宏源行业指数日行情，按月转换为月度序列；"
            r"“近 1 年”为 2026-09-24 对 2025 年 9 月的涨跌幅，"
            r"“2023 年初以来”的基期为 2023 年 1 月（约 3.75 年，因 2021 版行业分类自 2021-12-13 起实施）。"))


def t_vol() -> None:
    df = load("vol_summary")
    if df is None:
        return
    rows = df.to_dict("records")
    write("vol_summary", table(
        rows, caption="品种波动率与周期振幅（月度对数收益率年化，$\\sqrt{12}$；主窗口 2021-02～2026-08）",
        label="tab:vol", colspec=r"@{}lllrrrrrr@{}",
        headers=["代码", "品种", "大类", "主窗口年化波动\\%", "全样本年化波动\\%",
                 "主窗口最高", "主窗口最低", "主窗口峰谷比", "最长历史峰谷比"],
        src=r"月度对数收益率，年化因子 $\\sqrt{12}$；"
            r"主窗口为 2021-02～2026-08。"))


def main() -> None:
    t_fut_summary()
    t_hog_legs()
    t_hog_capacity()
    t_corr_group()
    t_corr_hog()
    t_leadlag()
    t_transmission()
    t_phase()
    t_phase_sw()
    t_sw_summary()
    t_vol()
    dat_fut_norm(out="fut_norm_grain.dat")
    dat_fut_norm(["SR", "CF", "CY", "RU", "NR", "AP", "CJ", "SP", "PK"],
                 start="2021-02-01", out="fut_norm_soft.dat")
    dat_vol()
    dat_phase_scatter()
    dat_sw_corr()
    dat_phase_bar("futures", "phase_same_fut.dat")
    print("done")


if __name__ == "__main__":
    main()
