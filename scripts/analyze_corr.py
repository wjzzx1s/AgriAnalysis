#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨品种周期相关性、领先滞后与周期阶段分析（以猪周期为基准）。

方法要点（避免常见的伪相关与样本错配）：
  1. 所有相关系数在同一时间窗口、同一频率上计算，绝不在不同样本期上比较。
     主窗口 2021-02～2026-08（生猪期货上市后的完整月份），长窗口 2015-02～2026-08。
  2. 收益率相关用月度对数收益率与季度（3 个月）对数收益率两套口径；季度口径噪声更低。
  3. 周期同步性用“周期分量”（价格对 12 个月移动平均的偏离）计算，可过滤长期趋势与通胀。
  4. 领先滞后在周期分量上做互相关，滞后阶限制在 ±12 个月，且要求有效样本 ≥ 48 个月，
     显著性阈值取 1.96/sqrt(n)；否则不报告。
  5. 阶段收益：用生猪价格的峰谷划分上涨/下跌段，统计各品种在各段的平均月度收益，
     检验“同一周期内谁同涨同跌”。

产出：
  data/clean/corr_m_*.dat/csv     月度收益率相关矩阵（pgfplots 热力图用）
  data/clean/corr_q_*.csv         季度收益率相关矩阵
  data/clean/corr_cyc_*.csv       周期分量相关矩阵
  data/clean/leadlag_*.dat/csv    领先滞后互相关
  data/clean/cycle_phase_*.csv    阶段收益统计
  notes/corr_summary.md           结论摘要
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agri_meta import FUT_META, INACTIVE, SW_L1, SW_L2, SW_L3  # noqa: E402
from common import CLEAN, NOTES, load_raw  # noqa: E402

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)

WIN_SHORT = ("2021-02-01", "2026-08-31")   # 生猪期货上市后的完整月份
WIN_LONG = ("2015-02-01", "2026-08-31")
OUT: list[str] = []


def log(s: str = "") -> None:
    print(s)
    OUT.append(s)


def dec_year(ts) -> float:
    t = pd.Timestamp(ts)
    return round(t.year + (t.month - 1) / 12 + (t.day - 1) / 365.25, 4)


def write_dat(name: str, xs, ys, header: str = "xy") -> None:
    """写出 pgfplots 可直读的两列数据文件。"""
    with open(os.path.join(CLEAN, f"{name}.dat"), "w", encoding="utf-8") as fh:
        fh.write(f"# {header}\n")
        for x, y in zip(xs, ys):
            if y is None or (isinstance(y, float) and np.isnan(y)):
                continue
            fh.write(f"{x} {y:.4f}\n")


# ------------------------------------------------------------------ 序列装载
def fut_monthly() -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for sym in FUT_META:
        df = load_raw(f"fut_{sym}")
        if df is None or df.empty:
            continue
        df["日期"] = pd.to_datetime(df["日期"])
        df["收盘价"] = pd.to_numeric(df["收盘价"], errors="coerce")
        s = df.set_index("日期")["收盘价"].dropna().resample("ME").mean()
        out[sym] = s
    return out


def sw_monthly() -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for code in {**SW_L1, **SW_L2, **SW_L3}:
        df = load_raw(f"sw_hist_{code}_day")
        if df is None or df.empty:
            continue
        s = pd.Series(pd.to_numeric(df["收盘"], errors="coerce").values,
                      index=pd.to_datetime(df["日期"].values)).dropna()
        out[code] = s.resample("ME").last()
    return out


# ------------------------------------------------------------------ 基础统计量
def logret(s: pd.Series, k: int = 1) -> pd.Series:
    r = np.log(s / s.shift(k))
    return r.replace([np.inf, -np.inf], np.nan).dropna()


def cyc_component(s: pd.Series, win: int = 12) -> pd.Series:
    """周期分量：价格对 12 个月移动平均的偏离（对数比），已去趋势。"""
    ma = s.rolling(win, min_periods=win).mean()
    return np.log(s / ma).replace([np.inf, -np.inf], np.nan)


def cut(s: pd.Series, win: tuple[str, str]) -> pd.Series:
    return s[(s.index >= pd.Timestamp(win[0])) & (s.index <= pd.Timestamp(win[1]))]


def corr_table(series: dict[str, pd.Series], win, min_obs: int = 48) -> pd.DataFrame:
    cols = {}
    for k, s in series.items():
        r = cut(s, win).dropna()
        if len(r) >= min_obs:
            cols[k] = r
    if len(cols) < 2:
        return pd.DataFrame()
    df = pd.DataFrame(cols)
    return df.corr(min_periods=min_obs)


def write_heat(name: str, corr: pd.DataFrame, labels: list[str]) -> None:
    with open(os.path.join(CLEAN, f"{name}.dat"), "w", encoding="utf-8") as fh:
        fh.write("i j rho\n")
        for i, a in enumerate(corr.index):
            for j, b in enumerate(corr.columns):
                v = corr.loc[a, b]
                if pd.notna(v):
                    fh.write(f"{i} {j} {v:.4f}\n")
    with open(os.path.join(CLEAN, f"{name}_labels.dat"), "w", encoding="utf-8") as fh:
        for i, lb in enumerate(labels):
            fh.write(f"{i} {lb}\n")


def top_pairs(corr: pd.DataFrame, k: int = 12) -> pd.DataFrame:
    rows = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            v = corr.loc[a, b]
            if pd.notna(v):
                rows.append({"A": FUT_META.get(a, (a,))[0] if a in FUT_META else a,
                             "B": FUT_META.get(b, (b,))[0] if b in FUT_META else b,
                             "ρ": v})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    t = t.reindex(t["ρ"].abs().sort_values(ascending=False).index)
    return t.head(k).round(3)


def ols_hac(y: np.ndarray, x: np.ndarray, lag: int = 6) -> tuple[float, float]:
    """单变量 OLS + Newey-West(1987) HAC 稳健标准误，返回 (斜率, t 值)。"""
    n = len(y)
    if n < 20:
        return (np.nan, np.nan)
    xm, ym = x.mean(), y.mean()
    xc, yc = x - xm, y - ym
    sxx = float(xc @ xc)
    if sxx <= 0:
        return (np.nan, np.nan)
    b = float(xc @ yc) / sxx
    a = ym - b * xm
    u = y - (a + b * x)
    # HAC 方差：sum_{j=-L}^{L} (1 - |j|/(L+1)) * sum_t xc_t u_t xc_{t-j} u_{t-j}
    s = 0.0
    for j in range(-lag, lag + 1):
        w = 1.0 - abs(j) / (lag + 1.0)
        if j >= 0:
            t1 = xc[j:] * u[j:]
            t2 = xc[:n - j] * u[:n - j]
        else:
            t1 = xc[:n + j] * u[:n + j]
            t2 = xc[-j:] * u[-j:]
        s += w * float(t1 @ t2)
    var_b = s / (sxx ** 2)
    if var_b <= 0:
        return (b, np.nan)
    return (b, b / np.sqrt(var_b))


def zigzag_kept(s: pd.Series, pct: float = 0.20, w: int = 2) -> list[tuple]:
    """返回 ZigZag 保留的转折点序列 [(时间戳, 价格), ...]（含首尾）。"""
    idx = list(s.index)
    val = [float(x) for x in s.values]
    n = len(val)
    if n < 2 * w + 3:
        return []
    ext: list[tuple] = []
    for i in range(w, n - w):
        win = val[i - w:i + w + 1]
        if val[i] == max(win) and val[i] > min(win):
            ext.append((idx[i], val[i], "H"))
        elif val[i] == min(win) and val[i] < max(win):
            ext.append((idx[i], val[i], "L"))
    merged: list[tuple] = []
    for e in ext:
        if merged and merged[-1][2] == e[2]:
            if (e[2] == "H" and e[1] > merged[-1][1]) or \
               (e[2] == "L" and e[1] < merged[-1][1]):
                merged[-1] = e
        else:
            merged.append(e)
    pts = [(idx[0], val[0], "S")] + merged + [(idx[-1], val[-1], "E")]
    kept: list[tuple] = [(pts[0][0], pts[0][1])]
    for e in pts[1:]:
        if len(kept) == 1:
            kept.append((e[0], e[1]))
            continue
        prev, prev2 = kept[-1], kept[-2]
        same_dir = (e[1] - prev[1]) * (prev[1] - prev2[1]) > 0
        if same_dir:
            if abs(e[1] - prev2[1]) > abs(prev[1] - prev2[1]):
                kept[-1] = (e[0], e[1])
        else:
            if abs(e[1] / prev[1] - 1) >= pct:
                kept.append((e[0], e[1]))
    return kept


def zigzag(s: pd.Series, pct: float = 0.20, w: int = 2) -> pd.DataFrame:
    """ZigZag 主周期段识别（三步法）：局部极值 → 同类合并 → 幅度过滤。

    1. 以 ±w 个月窗口取局部极大 / 极小点；
    2. 相邻同类极值只保留更极端者；
    3. 交替方向的两点间幅度不足 pct 的中间点被忽略（这一层过滤掉了噪声波动），
       同方向的更极端点则替换前一个点。
    返回：起点、终点、方向、月数、幅度%。
    """
    kept = zigzag_kept(s, pct=pct, w=w)
    rows = []
    for i in range(len(kept) - 1):
        d0, v0 = kept[i]
        d1, v1 = kept[i + 1]
        rows.append({"起点": pd.Timestamp(d0), "终点": pd.Timestamp(d1),
                     "起点价": round(v0, 2), "终点价": round(v1, 2),
                     "方向": "上涨" if v1 > v0 else "下跌",
                     "月数": round((pd.Timestamp(d1) - pd.Timestamp(d0)).days / 30.44, 1),
                     "幅度%": round((v1 / v0 - 1) * 100, 1)})
    return pd.DataFrame(rows)


def cycle_stats(legs: pd.DataFrame, label: str = "") -> str:
    """由 ZigZag 段统计：上行/下行时长与幅度、谷→谷完整周期长度。"""
    if legs.empty:
        return f"{label}：无有效周期段"
    up = legs[legs["方向"] == "上涨"]
    dn = legs[legs["方向"] == "下跌"]
    troughs = legs[legs["方向"] == "上涨"]["起点"]        # 每次上行段的起点即谷
    cyc = []
    tl = list(troughs)
    for i in range(len(tl) - 1):
        cyc.append((pd.Timestamp(tl[i + 1]) - pd.Timestamp(tl[i])).days / 30.44)
    n_cycle = len(cyc)
    avg_cyc = sum(cyc) / n_cycle if n_cycle else float("nan")
    return (f"{label}：上行段 {len(up)} 段、平均 {up['月数'].mean():.1f} 个月、"
            f"平均幅度 {up['幅度%'].mean():+.0f}%；下行段 {len(dn)} 段、"
            f"平均 {dn['月数'].mean():.1f} 个月、平均幅度 {dn['幅度%'].mean():+.0f}%；"
            f"谷→谷完整周期 {n_cycle} 个（数据内），平均长度 {avg_cyc:.1f} 个月")


# ------------------------------------------------------------------ 主流程
def main() -> None:
    fm = fut_monthly()
    sw = sw_monthly()
    log("# 跨品种周期相关性与阶段分析（analyze_corr.py 自动生成）\n")

    # ---------- 1. 月度收益率相关（主窗口 / 长窗口） ----------
    mr = {k: logret(v) for k, v in fm.items()}
    c_short = corr_table(mr, WIN_SHORT, min_obs=48)
    c_long = corr_table({k: v for k, v in mr.items() if k not in INACTIVE},
                        WIN_LONG, min_obs=100)
    log("## 1. 月度收益率相关矩阵\n")
    log(f"- 主窗口 {WIN_SHORT[0][:7]}～{WIN_SHORT[1][:7]}：{len(c_short)} 个品种，"
        f"观测 {len(cut(next(iter(mr.values())), WIN_SHORT))} 个月度点")
    log(f"- 长窗口 {WIN_LONG[0][:7]}～{WIN_LONG[1][:7]}：{len(c_long)} 个品种")
    log(f"- 5% 显著阈值：主窗口 |ρ|>0.24，长窗口 |ρ|>0.14")

    if not c_short.empty:
        labels = [FUT_META[s][0] for s in c_short.columns]
        c_short.round(3).to_csv(f"{CLEAN}/corr_m_short.csv", encoding="utf-8-sig")
        write_heat("corr_m_short", c_short, labels)
        log("\n- 主窗口下相关性最高与最低的组合（|ρ| 排序，前 10）：")
        log(top_pairs(c_short, 10).to_string(index=False))
        if "LH" in c_short.index:
            s = c_short["LH"].drop("LH").sort_values(ascending=False)
            log("\n- 与生猪期货的月度收益相关性（降序）：")
            log("  " + "；".join(f"{FUT_META[k][0]} {v:+.2f}" for k, v in s.items()))
            with open(f"{CLEAN}/corr_with_hog.dat", "w", encoding="utf-8") as fh:
                fh.write("i rho label\n")
                for i, (k, v) in enumerate(s.items()):
                    fh.write(f"{i} {v:.4f} {FUT_META[k][0]}\n")

    if not c_long.empty:
        c_long.round(3).to_csv(f"{CLEAN}/corr_m_long.csv", encoding="utf-8-sig")
        labels = [FUT_META[s][0] for s in c_long.columns]
        write_heat("corr_m_long", c_long, labels)

    # ---------- 2. 季度收益率相关（降噪口径） ----------
    qr = {k: logret(v, 3) for k, v in fm.items()}
    c_q = corr_table(qr, WIN_SHORT, min_obs=18)
    log("\n## 2. 季度（3 个月）收益率相关矩阵\n")
    if not c_q.empty:
        c_q.round(3).to_csv(f"{CLEAN}/corr_q_short.csv", encoding="utf-8-sig")
        labels = [FUT_META[s][0] for s in c_q.columns]
        write_heat("corr_q_short", c_q, labels)
        log(f"- 品种数 {len(c_q)}；5% 显著阈值 |ρ|>0.46（n≈20）")
        log("- 与生猪期货的季度收益相关性（|ρ| 降序）：")
        if "LH" in c_q.index:
            s = c_q["LH"].drop("LH")
            s = s.reindex(s.abs().sort_values(ascending=False).index)
            log("  " + "；".join(f"{FUT_META[k][0]} {v:+.2f}" for k, v in s.items()))

    # ---------- 3. 周期分量相关（去趋势，捕捉周期同步性） ----------
    cy = {k: cyc_component(v) for k, v in fm.items()}
    c_cy = corr_table(cy, WIN_SHORT, min_obs=48)
    log("\n## 3. 周期分量（价格对 12 个月均线的偏离）相关矩阵\n")
    if not c_cy.empty:
        c_cy.round(3).to_csv(f"{CLEAN}/corr_cyc_short.csv", encoding="utf-8-sig")
        labels = [FUT_META[s][0] for s in c_cy.columns]
        write_heat("corr_cyc_short", c_cy, labels)
        if "LH" in c_cy.index:
            s = c_cy["LH"].drop("LH").sort_values(ascending=False)
            log("- 与生猪周期分量的相关性（降序）：")
            log("  " + "；".join(f"{FUT_META[k][0]} {v:+.2f}" for k, v in s.items()))
            with open(f"{CLEAN}/corr_cyc_hog.dat", "w", encoding="utf-8") as fh:
                fh.write("i rho label\n")
                order = s.reindex(s.abs().sort_values(ascending=False).index)
                for i, (k, v) in enumerate(order.items()):
                    fh.write(f"{i} {v:.4f} {FUT_META[k][0]}\n")

    # ---------- 4. 领先滞后（周期分量，限制 ±12 月） ----------
    log("\n## 4. 领先滞后互相关（周期分量，±12 个月）\n")
    rows = []
    if "LH" in cy:
        base = cut(cy["LH"], WIN_SHORT).dropna()
        for sym in cy:
            if sym == "LH" or sym in INACTIVE:
                continue
            other = cut(cy[sym], WIN_SHORT).dropna()
            vals = []
            for lag in range(-12, 13):
                x = base.shift(lag)
                pair = pd.concat([x, other], axis=1, sort=True).dropna()
                n = len(pair)
                if n < 48:
                    continue
                r = pair.iloc[:, 0].corr(pair.iloc[:, 1])
                crit = 1.96 / np.sqrt(n)
                vals.append((lag, r, n, abs(r) > crit))
            if len(vals) < 13:
                continue
            with open(f"{CLEAN}/leadlag2_{sym}.dat", "w", encoding="utf-8") as fh:
                fh.write(f"lag rho n sig\n")
                for lag, r, n, sig in vals:
                    fh.write(f"{lag} {r:.4f} {n} {1 if sig else 0}\n")
            sig_vals = [v for v in vals if v[3]]
            if not sig_vals:
                rows.append({"品种": FUT_META[sym][0], "代码": sym,
                             "大类": FUT_META[sym][1], "同期相关": round(dict(
                                 (l, r) for l, r, _, _ in vals).get(0, np.nan), 3),
                             "最大显著相关": np.nan, "滞后月": np.nan,
                             "判定": "无显著领先滞后关系"})
                continue
            best = max(sig_vals, key=lambda v: abs(v[1]))
            rows.append({"品种": FUT_META[sym][0], "代码": sym,
                         "大类": FUT_META[sym][1],
                         "同期相关": round(dict((l, r) for l, r, _, _ in vals).get(0, np.nan), 3),
                         "最大显著相关": round(best[1], 3), "滞后月": best[0],
                         "判定": ("生猪领先" if best[0] > 0 else
                                  ("生猪滞后" if best[0] < 0 else "同步"))})
    t = pd.DataFrame(rows)
    if not t.empty:
        t = t.reindex(t["最大显著相关"].abs().sort_values(ascending=False).index)
        t.to_csv(f"{CLEAN}/leadlag2_summary.csv", index=False, encoding="utf-8-sig")
        log(t.to_string(index=False))
        log("\n说明：滞后月 $k>0$ 表示该品种滞后生猪 $k$ 个月（生猪领先），"
            "$k<0$ 表示该品种领先生猪。仅报告通过 5% 显著性的滞后阶。")

    # ---------- 4b. 传导回归：生猪收益（滞后 k 月）→ 各品种收益 ----------
    log("\n## 4b. 传导回归检验（HAC/Newey-West 稳健标准误）\n")
    log("模型：$r^{i}_t = \\alpha + \\beta_k\\, r^{\\text{LH}}_{t-k} + \\varepsilon_t$，"
        "Newey-West 滞后阶 6；报告 $\\beta$ 的显著性（5%）。")
    if "LH" in mr:
        x_all = cut(mr["LH"], WIN_SHORT).dropna()
        rows = []
        for sym in mr:
            if sym == "LH" or sym in INACTIVE:
                continue
            y_all = cut(mr[sym], WIN_SHORT).dropna()
            best = None
            sig_list = []
            for k in range(0, 13):
                x = x_all.shift(k)
                pair = pd.concat([y_all, x], axis=1, sort=True).dropna()
                if len(pair) < 40:
                    continue
                b, t = ols_hac(pair.iloc[:, 0].values, pair.iloc[:, 1].values, lag=6)
                if t is not None and abs(t) > 1.96:
                    sig_list.append((k, b, t))
                    if best is None or abs(t) > abs(best[2]):
                        best = (k, b, t)
            rows.append({"品种": FUT_META[sym][0], "代码": sym, "大类": FUT_META[sym][1],
                         "显著滞后阶": len(sig_list),
                         "最优滞后k(月)": best[0] if best else np.nan,
                         "β": round(best[1], 3) if best else np.nan,
                         "t值": round(best[2], 2) if best else np.nan,
                         "显著k清单": ",".join(str(s[0]) for s in sig_list) or "无"})
            with open(f"{CLEAN}/trans_{sym}.dat", "w", encoding="utf-8") as fh:
                fh.write("k beta t\n")
                for k in range(0, 13):
                    x = x_all.shift(k)
                    pair = pd.concat([y_all, x], axis=1, sort=True).dropna()
                    if len(pair) < 40:
                        continue
                    b, t = ols_hac(pair.iloc[:, 0].values, pair.iloc[:, 1].values, lag=6)
                    fh.write(f"{k} {b:.4f} {t:.4f}\n")
        tr = pd.DataFrame(rows)
        tr = tr.sort_values(["显著滞后阶", "t值"], ascending=False)
        tr.to_csv(f"{CLEAN}/transmission_summary.csv", index=False, encoding="utf-8-sig")
        log(tr.to_string(index=False))

    # ---------- 4c. 稳健性：分样本相关性 ----------
    log("\n## 4c. 稳健性检验：分样本相关性（月度收益率）\n")
    if "LH" in mr:
        halves = [("2021-02-01", "2023-12-31"), ("2024-01-01", "2026-08-31")]
        rows = []
        for sym in mr:
            if sym == "LH" or sym in INACTIVE:
                continue
            x = mr[sym]
            r1 = cut(x, halves[0]).dropna()
            r2 = cut(x, halves[1]).dropna()
            h1 = cut(mr["LH"], halves[0]).dropna()
            h2 = cut(mr["LH"], halves[1]).dropna()
            p1 = pd.concat([r1, h1], axis=1, sort=True).dropna()
            p2 = pd.concat([r2, h2], axis=1, sort=True).dropna()
            if len(p1) < 12 or len(p2) < 12:
                continue
            rows.append({"品种": FUT_META[sym][0], "代码": sym,
                         "2021-2023相关": round(p1.iloc[:, 0].corr(p1.iloc[:, 1]), 2),
                         "2024-2026相关": round(p2.iloc[:, 0].corr(p2.iloc[:, 1]), 2),
                         "n1": len(p1), "n2": len(p2)})
        rb = pd.DataFrame(rows)
        rb["符号一致"] = np.where(rb["2021-2023相关"] * rb["2024-2026相关"] > 0, "是", "否")
        rb = rb.reindex(rb[["2021-2023相关", "2024-2026相关"]].abs().max(axis=1)
                        .sort_values(ascending=False).index)
        rb.to_csv(f"{CLEAN}/corr_robustness.csv", index=False, encoding="utf-8-sig")
        log(rb.to_string(index=False))
        log(f"\n- 两段样本符号一致的品种占比："
            f"{(rb['符号一致'] == '是').mean() * 100:.0f}%"
            f"（{int((rb['符号一致'] == '是').sum())}/{len(rb)}）")

    # ---------- 4d. 长样本基准：生猪现货价格指数（2015 年至今，约 3 个猪周期） ----------
    log("\n## 4d. 长样本检验：以生猪现货价格指数为基准（2015 年至今）\n")
    hog_spot = load_raw("hog_spot_index")
    hs_m = None
    if hog_spot is not None and len(hog_spot):
        hog_spot["日期"] = pd.to_datetime(hog_spot["日期"])
        col = "指数" if "指数" in hog_spot.columns else hog_spot.columns[1]
        v = pd.to_numeric(hog_spot[col], errors="coerce")
        hs = pd.Series(v.values, index=hog_spot["日期"]).dropna()
        hs_m = hs.resample("ME").mean().dropna()
        log(f"- 生猪现货价格指数：{hs.index.min():%Y-%m-%d} 至 {hs.index.max():%Y-%m-%d}，"
            f"周度观测 {len(hs)} 个，月度 {len(hs_m)} 个；最新 {hs.iloc[-1]:.2f}")
        write_dat("hog_spot_monthly", [dec_year(t) for t in hs_m.index], hs_m.values,
                  header="生猪现货价格指数（月度均值）")
    if hs_m is not None:
        hrs = logret(hs_m)
        rows = []
        for sym in mr:
            if sym in INACTIVE:
                continue
            r = logret(fm[sym])
            pair = pd.concat([r, hrs], axis=1, sort=True).dropna()
            if len(pair) < 60:
                continue
            corr = pair.iloc[:, 0].corr(pair.iloc[:, 1])
            # 长样本传导回归
            best = None
            sig = []
            for k in range(0, 19):
                x = hrs.shift(k)
                pp = pd.concat([r, x], axis=1, sort=True).dropna()
                if len(pp) < 60:
                    continue
                b, t = ols_hac(pp.iloc[:, 0].values, pp.iloc[:, 1].values, lag=9)
                if t is not None and abs(t) > 1.96:
                    sig.append((k, b, t))
                    if best is None or abs(t) > abs(best[2]):
                        best = (k, b, t)
            rows.append({"品种": FUT_META[sym][0], "代码": sym, "大类": FUT_META[sym][1],
                         "样本月数": len(pair),
                         "与猪价相关": round(corr, 3),
                         "显著滞后阶数": len(sig),
                         "最优k": best[0] if best else np.nan,
                         "β": round(best[1], 3) if best else np.nan,
                         "t值": round(best[2], 2) if best else np.nan})
        lt = pd.DataFrame(rows)
        lt = lt.reindex(lt["与猪价相关"].abs().sort_values(ascending=False).index)
        lt.to_csv(f"{CLEAN}/corr_long_hogspot.csv", index=False, encoding="utf-8-sig")
        log("- 长样本（2015 年至今）与生猪现货价格的相关性与传导：")
        log(lt.to_string(index=False))
        log(f"- 5% 显著阈值（n≈130）：|ρ|>0.17")

        # 长样本阶段分析（ZigZag 20% 阈值）
        legs_df = zigzag(hs_m, pct=0.20)
        legs_df["起点"] = legs_df["起点"].dt.strftime("%Y-%m")
        legs_df["终点"] = legs_df["终点"].dt.strftime("%Y-%m")
        legs_df.to_csv(f"{CLEAN}/hog_legs_long.csv", index=False, encoding="utf-8-sig")
        log("\n- 长样本猪周期分段（现货指数，ZigZag 20% 阈值）：")
        log(legs_df.to_string(index=False))
        log("- " + cycle_stats(zigzag(hs_m, pct=0.20), "现货猪周期（2015 年至今）"))
        # ZigZag 折线（供 pgfplots 直接绘制周期骨架）
        piv = zigzag_kept(hs_m, pct=0.20)
        write_dat("hog_zigzag_spot", [dec_year(d) for d, _ in piv], [v for _, v in piv],
                  header="生猪现货价格指数 ZigZag（月度）")

        lab = pd.Series(index=hrs.index, dtype=object)
        for _, L in legs_df.iterrows():
            m0 = pd.Timestamp(L["起点"] + "-01")
            m1 = pd.Timestamp(L["终点"] + "-01")
            lab.loc[(lab.index > m0) & (lab.index <= m1)] = L["方向"]
        lab = lab.dropna()
        rows = []
        for sym in fm:
            if sym in INACTIVE:
                continue
            r = logret(fm[sym])
            rr = r.reindex(lab.index).dropna()
            ll = lab.reindex(rr.index)
            up, dn = rr[ll == "上涨"], rr[ll == "下跌"]
            if len(up) < 15 or len(dn) < 15:
                continue
            pair = pd.concat([rr, hrs.reindex(rr.index)], axis=1, sort=True).dropna()
            same = float((np.sign(pair.iloc[:, 0]) == np.sign(pair.iloc[:, 1])).mean()) * 100
            rows.append({"品种": FUT_META[sym][0], "代码": sym, "大类": FUT_META[sym][1],
                         "上涨段月均%": round(up.mean() * 100, 2),
                         "下跌段月均%": round(dn.mean() * 100, 2),
                         "差值pp": round((up.mean() - dn.mean()) * 100, 2),
                         "同向月占比%": round(same, 1),
                         "上涨月数": len(up), "下跌月数": len(dn)})
        ph2 = pd.DataFrame(rows).sort_values("差值pp", ascending=False)
        ph2.to_csv(f"{CLEAN}/cycle_phase_long.csv", index=False, encoding="utf-8-sig")
        log("\n- 长样本阶段收益（生猪现货上涨段 vs 下跌段）：")
        log(ph2.to_string(index=False))
        with open(f"{CLEAN}/phase_diff_long.dat", "w", encoding="utf-8") as fh:
            fh.write("# i diff label\n")
            for i, (_, r) in enumerate(ph2.iterrows()):
                fh.write(f"{i} {r['差值pp']:.4f} {r['品种']}\n")

    # ---------- 5. 阶段收益（按生猪周期峰谷划分） ----------
    log("\n## 5. 猪周期阶段与各品种阶段收益\n")
    phase = None
    if "LH" in fm:
        lh = fm["LH"].dropna()
        legs_raw = zigzag(lh[lh.index >= pd.Timestamp("2021-01-01")], pct=0.18)
        legs_df = legs_raw.copy()
        if not legs_df.empty:
            legs_df["起点"] = legs_df["起点"].dt.strftime("%Y-%m")
            legs_df["终点"] = legs_df["终点"].dt.strftime("%Y-%m")
        legs_df.to_csv(f"{CLEAN}/hog_legs.csv", index=False, encoding="utf-8-sig")
        log("- 生猪期货（2021 年上市至今）ZigZag 18% 阈值分段：")
        log(legs_df.to_string(index=False))
        log("- " + cycle_stats(legs_raw, "期货猪周期（2021 年至今）"))
        piv_lh = zigzag_kept(lh[lh.index >= pd.Timestamp("2021-01-01")], pct=0.18)
        write_dat("hog_zigzag_lh", [dec_year(d) for d, _ in piv_lh], [v for _, v in piv_lh],
                  header="生猪期货主力连续 ZigZag（月度，元/吨）")

        # 用月份区间给每个月的生猪收益率打上方向标签
        lab = pd.Series(index=mr["LH"].index, dtype=object)
        for _, L in legs_df.iterrows():
            m0 = pd.Timestamp(L["起点"] + "-01")
            m1 = pd.Timestamp(L["终点"] + "-01")
            lab.loc[(lab.index > m0) & (lab.index <= m1)] = L["方向"]
        lab = lab.dropna()

        rows = []
        hog_r = mr.get("LH")
        for sym, r in mr.items():
            rr = r.reindex(lab.index).dropna()
            ll = lab.reindex(rr.index)
            up = rr[ll == "上涨"]
            dn = rr[ll == "下跌"]
            if len(up) < 6 or len(dn) < 6:
                continue
            same_rate = np.nan
            if hog_r is not None and sym != "LH":
                pair = pd.concat([rr, hog_r.reindex(rr.index)], axis=1, sort=True).dropna()
                if len(pair) >= 12:
                    same_rate = round(float((np.sign(pair.iloc[:, 0]) ==
                                             np.sign(pair.iloc[:, 1])).mean()) * 100, 1)
            rows.append({"品种": FUT_META[sym][0], "代码": sym, "大类": FUT_META[sym][1],
                         "上涨段月均收益%": round(up.mean() * 100, 2),
                         "下跌段月均收益%": round(dn.mean() * 100, 2),
                         "差值(pp)": round((up.mean() - dn.mean()) * 100, 2),
                         "与猪价同向月占比%": same_rate,
                         "上涨月数": len(up), "下跌月数": len(dn)})
        ph = pd.DataFrame(rows)
        if not ph.empty:
            ph.to_csv(f"{CLEAN}/cycle_phase_futures.csv", index=False,
                      encoding="utf-8-sig")
            log("\n- 各品种在生猪上涨段 / 下跌段的月均对数收益：")
            log(ph.sort_values("差值(pp)", ascending=False).to_string(index=False))
            with open(f"{CLEAN}/phase_diff.dat", "w", encoding="utf-8") as fh:
                fh.write("# i diff label\n")
                sd = ph.sort_values("差值(pp)", ascending=False)
                for i, (_, r) in enumerate(sd.iterrows()):
                    fh.write(f"{i} {r['差值(pp)']:.4f} {r['品种']}\n")

        # 申万行业指数在同样阶段的表现
        rows = []
        for code, s2 in sw.items():
            r = logret(s2)
            rr = r.reindex(lab.index).dropna()
            ll = lab.reindex(rr.index)
            up, dn = rr[ll == "上涨"], rr[ll == "下跌"]
            if len(up) < 6 or len(dn) < 6:
                continue
            nm = {**SW_L1, **SW_L2, **SW_L3}.get(code, code)
            rows.append({"行业代码": code, "行业名称": nm,
                         "层级": "一级" if code in SW_L1 else ("二级" if code in SW_L2 else "三级"),
                         "上涨段月均收益%": round(up.mean() * 100, 2),
                         "下跌段月均收益%": round(dn.mean() * 100, 2),
                         "差值(pp)": round((up.mean() - dn.mean()) * 100, 2)})
        swp = pd.DataFrame(rows)
        if not swp.empty:
            swp.to_csv(f"{CLEAN}/cycle_phase_sw.csv", index=False, encoding="utf-8-sig")
            log("\n- 申万农业子行业指数在生猪上涨段 / 下跌段的月均收益：")
            log(swp.sort_values("差值(pp)", ascending=False).to_string(index=False))

    # ---------- 6. 波动率与周期振幅汇总 ----------
    log("\n## 6. 品种波动率与周期振幅\n")
    rows = []
    for sym, s in fm.items():
        s2 = cut(s, WIN_SHORT)
        r = logret(s)
        r2 = cut(r, WIN_SHORT)
        if len(s2) < 24:
            continue
        rows.append({"代码": sym, "品种": FUT_META[sym][0], "大类": FUT_META[sym][1],
                     "主窗口年化波动%": round(r2.std() * np.sqrt(12) * 100, 1),
                     "全样本年化波动%": round(r.std() * np.sqrt(12) * 100, 1),
                     "主窗口最高": round(s2.max(), 1), "主窗口最低": round(s2.min(), 1),
                     "主窗口峰谷比": round(s2.max() / s2.min(), 2),
                     "最长历史峰谷比": round(s.max() / s.min(), 2)})
    vol = pd.DataFrame(rows).sort_values("主窗口年化波动%", ascending=False)
    vol.to_csv(f"{CLEAN}/vol_summary.csv", index=False, encoding="utf-8-sig")
    log(vol.to_string(index=False))

    with open(os.path.join(NOTES, "corr_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n>> 已写入 notes/corr_summary.md（{len(OUT)} 行）")


if __name__ == "__main__":
    main()
