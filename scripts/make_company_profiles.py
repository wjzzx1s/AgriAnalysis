#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""生成第二部分“农业上市公司画像”的逐公司数据与 LaTeX 片段。

对申万农林牧渔（801010）全部 A 股上市公司逐家生成画像：
  公司基本情况 / 历史股价 / 过去周期分析 / 盈利情况 / 财务分析 /
  重大战略转型 / 历史融投资情况 / 未来潜在融资需求分析

产出
  data/clean/company_profiles.csv         每家公司一行的画像指标（含 2026 中报）
  data/clean/profiles/px_<code>.dat       月度收盘价（元/股）
  data/clean/profiles/pxzz_<code>.dat     月度收盘价的 ZigZag 周期骨架
  tex/gen/profiles/<group>.tex            逐公司 LaTeX 片段（按行业分组 \input）
  notes/company_profiles_summary.md       生成摘要（撰写正文时核对口径）
"""
from __future__ import annotations

import os
import sys
import re

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CLEAN, NOTES, RAW, ROOT  # noqa: E402
from make_company import EVENT_RULES, classify, fmt, num, rd, tex_escape  # noqa: E402
import company_facts as CF  # noqa: E402
import company_charts as CH  # noqa: E402

COMP = os.path.join(RAW, "company")
LEGACY = os.path.join(RAW, "company_legacy")
PROF = os.path.join(CLEAN, "profiles")
GENROOT = os.path.join(ROOT, "tex", "gen")
GEN = os.path.join(GENROOT, "profiles")
for d in (PROF, GEN):
    os.makedirs(d, exist_ok=True)

# 股价 ZigZag 阈值：股票波动大于商品，取 25%
ZZ_PCT = 0.25
ZZ_W = 2

# 报告期
YEARS = ["2021", "2022", "2023", "2024", "2025"]
TBL_YEARS = ["2023", "2024", "2025"]
H1 = "20260630"
H1_PREV = "20250630"
# 财务作图与融资分析使用的报告期（资产负债表/现金流量表口径）
FIN_ANNUAL = ["2021", "2022", "2023", "2024", "2025"]
FIN_DATES = [f"{y}1231" for y in FIN_ANNUAL] + [H1_PREV, H1]

LOG: list[str] = []


def log(s: str = "") -> None:
    LOG.append(s)
    print(s)


# ------------------------------------------------------------------ 基础工具
def dec_year(ts: pd.Timestamp) -> float:
    """月份中心对应的十进制年份（供 pgfplots 使用）。"""
    return ts.year + (ts.month - 0.5) / 12.0


def zz(x, nd: int = 2) -> str:
    """带正负号的百分数文本。"""
    try:
        v = float(x)
        if not np.isfinite(v):
            return "—"
        return f"{v:+.{nd}f}%"
    except (TypeError, ValueError):
        return "—"


def yi(v, nd: int = 2) -> str:
    """亿元文本。"""
    try:
        f = float(v)
        if not np.isfinite(f):
            return "—"
        return f"{f:,.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def ym(ts) -> str:
    try:
        t = pd.Timestamp(ts)
    except (TypeError, ValueError):
        return "—"
    return f"{t.year} 年 {t.month} 月"


def dash(v, nd: int = 1, suffix: str = "") -> str:
    try:
        f = float(v)
        if not np.isfinite(f):
            return "—"
        return f"{f:.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


# ------------------------------------------------------------------ ZigZag
def zigzag_kept(s: pd.Series, pct: float = ZZ_PCT, w: int = ZZ_W) -> list[tuple]:
    """ZigZag 保留的转折点（局部极值 → 同类合并 → 幅度过滤）。"""
    idx = list(s.index)
    val = [float(x) for x in s.values]
    n = len(val)
    if n < 2 * w + 3:
        return [(idx[0], val[0]), (idx[-1], val[-1])] if n else []
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
        if (e[1] - prev[1]) * (prev[1] - prev2[1]) > 0:
            if abs(e[1] - prev2[1]) > abs(prev[1] - prev2[1]):
                kept[-1] = (e[0], e[1])
        else:
            if prev[1] and abs(e[1] / prev[1] - 1) >= pct:
                kept.append((e[0], e[1]))
    return kept


def zigzag_legs(s: pd.Series, pct: float = ZZ_PCT) -> pd.DataFrame:
    kept = zigzag_kept(s, pct=pct)
    rows = []
    for i in range(len(kept) - 1):
        d0, v0 = kept[i]
        d1, v1 = kept[i + 1]
        rows.append({"起": pd.Timestamp(d0), "止": pd.Timestamp(d1),
                     "起价": v0, "止价": v1,
                     "方向": "上涨" if v1 > v0 else "下跌",
                     "月数": (pd.Timestamp(d1) - pd.Timestamp(d0)).days / 30.44,
                     "幅度": (v1 / v0 - 1) * 100 if v0 else np.nan})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 数据读取
def monthly_close(code: str) -> pd.Series | None:
    px = rd(code, "px")
    if px is None or not len(px):
        return None
    px = px.copy()
    px["date"] = pd.to_datetime(px["date"], errors="coerce")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px = px.dropna(subset=["date", "close"]).sort_values("date")
    if not len(px):
        return None
    s = px.set_index("date")["close"].resample("ME").last().dropna()
    return s if len(s) >= 6 else None


def load_index_dat(name: str) -> pd.Series:
    """读 data/clean 下的 (x, y) 月度序列，x 为十进制年份。"""
    p = os.path.join(CLEAN, name)
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    xs, ys = [], []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except (ValueError, IndexError):
                continue
    if not xs:
        return pd.Series(dtype=float)
    idx = [pd.Timestamp(int(x), max(1, min(12, int(round((x - int(x)) * 12 + 0.5)))), 1)
           for x in xs]
    return pd.Series(ys, index=pd.DatetimeIndex(idx))


def logret(s: pd.Series) -> pd.Series:
    s = s[s > 0]
    return np.log(s).diff().dropna()


def corr_monthly(a: pd.Series, b: pd.Series) -> float:
    a, b = logret(a), logret(b)
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(j) < 12:
        return float("nan")
    return float(j["a"].corr(j["b"]))


def metrics_of(fa: pd.DataFrame, metric: str, periods: list[str]) -> dict:
    """从财务摘要取某个指标的各期数值。"""
    out = {p: np.nan for p in periods}
    if fa is None or not len(fa):
        return out
    com = fa[(fa["选项"] == "常用指标") & (fa["指标"].astype(str).str.strip() == metric)]
    if not len(com):
        return out
    row = com.iloc[0]
    for p in periods:
        if p in row.index:
            out[p] = num(row[p])
    return out


def fin_ind_val(fi: pd.DataFrame, col: str, date: str) -> float:
    if fi is None or not len(fi) or col not in fi.columns:
        return float("nan")
    s = fi[fi["日期"].astype(str).str[:10] == date]
    return num(s.iloc[0][col]) if len(s) else float("nan")


# ------------------------------------------------- 资产负债表 / 现金流量表
def stmt_val(df: pd.DataFrame | None, col: str, date: str) -> float:
    """资产负债表/现金流量表中某一报告期的科目值（报告日形如 20260630）。"""
    if df is None or not len(df) or col not in df.columns or "报告日" not in df.columns:
        return float("nan")
    key = df["报告日"].astype(str).str.replace("-", "", regex=False).str[:8]
    s = df[key == date]
    return num(s.iloc[0][col]) if len(s) else float("nan")


def _sum(*vals) -> float:
    """求和：全部缺失记为缺失（不把缺失当 0）。"""
    v = [float(x) for x in vals if x is not None and np.isfinite(float(x))]
    return float(sum(v)) if v else float("nan")


def debt_metrics(code: str) -> dict:
    """逐期（年报 2021---2025 + 两个半年报）的偿债与融资科目。

    有息负债 = 短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券 + 租赁负债；
    短期债务 = 短期借款 + 一年内到期的非流动负债；现金短债比 = 货币资金 / 短期债务。
    现金流量表为年初至今累计口径（2026 年半年报为 1---6 月累计，未年化）。
    """
    bs, cf = rd(code, "bs"), rd(code, "cf")
    out: dict[str, dict] = {}
    for d in FIN_DATES:
        st = _sum(stmt_val(bs, "短期借款", d), stmt_val(bs, "一年内到期的非流动负债", d))
        lt = _sum(stmt_val(bs, "长期借款", d), stmt_val(bs, "应付债券", d),
                  stmt_val(bs, "租赁负债", d))
        cash = stmt_val(bs, "货币资金", d)
        ibd = _sum(st, lt)
        out[d] = {
            "货币资金": cash,
            "短期债务": st,
            "长期债务": lt,
            "有息负债": ibd,
            "净有息负债": (ibd - cash) if np.isfinite(ibd) and np.isfinite(cash) else np.nan,
            "现金短债比": (cash / st) if np.isfinite(cash) and np.isfinite(st) and st > 0 else np.nan,
            "总资产": stmt_val(bs, "资产总计", d),
            "存货": stmt_val(bs, "存货", d),
            "固定资产": stmt_val(bs, "固定资产净额", d),
            "在建工程": stmt_val(bs, "在建工程合计", d),
            "生产性生物资产": stmt_val(bs, "生产性生物资产", d),
            "商誉": stmt_val(bs, "商誉", d),
            "流动负债": stmt_val(bs, "流动负债合计", d),
            "负债合计": stmt_val(bs, "负债合计", d),
            "归母权益": stmt_val(bs, "归属于母公司股东权益合计", d),
            "经营现金流": stmt_val(cf, "经营活动产生的现金流量净额", d),
            "取得借款": stmt_val(cf, "取得借款收到的现金", d),
            "发行债券": stmt_val(cf, "发行债券收到的现金", d),
            "吸收投资": stmt_val(cf, "吸收投资收到的现金", d),
            "偿还债务": stmt_val(cf, "偿还债务支付的现金", d),
            "利息支付": stmt_val(cf, "分配股利、利润或偿付利息所支付的现金", d),
            "筹资净额": stmt_val(cf, "筹资活动产生的现金流量净额", d),
            "购建支出": stmt_val(cf, "购建固定资产、无形资产和其他长期资产所支付的现金", d),
        }
    return out


def fin_chart_series(r: dict) -> dict:
    """作图序列：年报 2021---2025 与 2026 年半年报（单位：亿元、%）。"""
    def yi_(v):
        return v / 1e8 if np.isfinite(v) else np.nan

    def g(key: str, period: str) -> float:
        return r.get(key, {}).get(period, np.nan)

    annual, h1 = {}, {}
    for y in FIN_ANNUAL:
        d = f"{y}1231"
        annual[y] = {
            "rev": yi_(g("营收", d)),
            "ni": yi_(g("归母", d)),
            "roe": g("ROE", d),
            "debt": g("负债率", d),
            "cash": yi_(r["债务"].get(d, {}).get("货币资金", np.nan)),
            "ibd": yi_(r["债务"].get(d, {}).get("有息负债", np.nan)),
            "ocf": yi_(g("现金流", d)),
        }
    h1 = {
        "rev": yi_(g("营收", H1)),
        "ni": yi_(g("归母", H1)),
        "roe": g("ROE", H1),
        "debt": g("负债率", H1),
        "cash": yi_(r["债务"].get(H1, {}).get("货币资金", np.nan)),
        "ibd": yi_(r["债务"].get(H1, {}).get("有息负债", np.nan)),
        "ocf": yi_(g("现金流", H1)),
    }
    return {"annual": annual, "h1": h1}


def composition(code: str) -> dict:
    """主营构成（按产品分类优先）：最近一期与 2021 年的结构与变化。"""
    p = os.path.join(LEGACY, f"{code}_zygc.csv")
    out = {"ok": False}
    if not os.path.exists(p):
        return out
    try:
        d = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    except Exception:  # noqa: BLE001
        return out
    if "报告日期" not in d.columns:
        return out
    d = d.copy()
    d["主营收入"] = pd.to_numeric(d["主营收入"], errors="coerce")
    d["收入比例"] = pd.to_numeric(d["收入比例"], errors="coerce")
    # 分类口径选择：优先取“各构成占比合计最接近 100%”的口径
    # （部分公司的“按产品分类”含内部销售抵消行，占比合计会明显偏离 100%）
    best, best_score = None, None
    for kind in ("按行业分类", "按产品分类"):
        sub = d[d["分类类型"] == kind]
        if not len(sub):
            continue
        tot = pd.to_numeric(sub[sub["报告日期"] == sub["报告日期"].max()]["收入比例"],
                            errors="coerce").sum()
        score = abs(float(tot) - 1.0) if np.isfinite(tot) else 9.9
        if best_score is None or score < best_score - 1e-9:
            best, best_score = kind, score
    if best is None:
        return out
    kind = best
    d = d[d["分类类型"] == kind]
    dates = sorted(d["报告日期"].unique())
    if not dates:
        return out
    latest = dates[-1]

    def top3(dt):
        s = d[d["报告日期"] == dt].copy()
        s = s[pd.to_numeric(s["收入比例"], errors="coerce") > 0]
        s = s.sort_values("主营收入", ascending=False)
        s = s[s["主营收入"].notna()]
        return [(str(r["主营构成"]), float(r["收入比例"]) * 100
                 if np.isfinite(r["收入比例"]) else np.nan) for _, r in s.head(3).iterrows()]

    t_new = top3(latest)
    t_old = top3("2021-12-31") or top3(dates[0])
    out.update({"ok": bool(t_new), "期": latest, "类别": kind, "新": t_new, "旧": t_old,
                "旧期": "2021-12-31" if "2021-12-31" in dates else dates[0],
                "合计": sum(v for _, v in t_new if np.isfinite(v))})
    if t_new and t_old:
        # 只在“真的换了块业务”时才算变化：两期口径的行业/产品命名常不同
        # （如 2021 年叫“生猪养殖”、2026 年叫“养殖”），这种标签差异不构成主业迁移
        _a, _b = str(t_old[0][0]), str(t_new[0][0])
        _same = (_a == _b) or (_a in _b) or (_b in _a)
        out["首位变化"] = not _same
        if np.isfinite(t_new[0][1]) and np.isfinite(t_old[0][1]):
            out["首位占比变化"] = t_new[0][1] - t_old[0][1]
    return out


def events_of(code: str, cutoff: str = "2023-09-01") -> dict:
    """公告分类计数与典型标题。"""
    ev = {name: 0 for name, _ in EVENT_RULES}
    titles: dict[str, list[str]] = {name: [] for name, _ in EVENT_RULES}
    dc = rd(code, "disc")
    n = 0
    if dc is not None and len(dc):
        dc = dc.copy()
        dc["公告时间"] = pd.to_datetime(dc["公告时间"], errors="coerce")
        dc = dc[dc["公告时间"] >= pd.Timestamp(cutoff)]
        n = len(dc)
        for t in dc["公告标题"].astype(str):
            for name in classify(t):
                ev[name] += 1
                if len(titles[name]) < 40:
                    titles[name].append(t)
    return {"n": n, "ev": ev, "titles": titles}


def share_history(code: str) -> dict:
    sc = rd(code, "share_chg")
    out = {"n2023": 0, "reasons": "", "last": "—", "first_total": np.nan,
           "last_total": np.nan, "raise": 0, "cb": 0}
    if sc is None or not len(sc):
        return out
    sc = sc.copy()
    sc["变动日期"] = pd.to_datetime(sc["变动日期"], errors="coerce")
    sc["总股本"] = pd.to_numeric(sc.get("总股本"), errors="coerce")
    sc = sc.dropna(subset=["变动日期"]).sort_values("变动日期")
    if not len(sc):
        return out
    recent = sc[sc["变动日期"] >= pd.Timestamp("2023-01-01")]
    out["n2023"] = len(recent)
    rs = recent["变动原因"].dropna().astype(str)
    cnt: dict[str, int] = {}
    for r in rs:
        for k in str(r).split(","):
            k = k.strip()
            if k and k != "定期报告":
                cnt[k] = cnt.get(k, 0) + 1
    out["reasons"] = "、".join(f"{k} {v} 次" for k, v in
                             sorted(cnt.items(), key=lambda x: -x[1])[:4])
    out["last"] = sc["变动日期"].iloc[-1]
    out["last_total"] = float(sc["总股本"].iloc[-1]) / 1e4 if np.isfinite(
        float(sc["总股本"].iloc[-1] or np.nan)) else np.nan
    base = sc[sc["变动日期"] <= pd.Timestamp("2021-12-31")]
    out["first_total"] = float((base if len(base) else sc)["总股本"].iloc[-1]) / 1e4 \
        if np.isfinite(float((base if len(base) else sc)["总股本"].iloc[-1] or np.nan)) else np.nan
    allr = sc["变动原因"].dropna().astype(str)
    out["raise"] = int(allr.str.contains("增发新股上市|配股|配售").sum())
    out["cb"] = int(allr.str.contains("可转债转股").sum())
    return out


def dividend_history(code: str) -> dict:
    """近三年现金分红：与 make_company.py（附录总表口径）采用同一筛选与同一单位。

    巨潮接口有两种表结构：一种含“报告期/方案进度/现金分红-现金分红比例”，
    另一种含“股权登记日/派息比例/报告时间”。两者的金额列均为**每 10 股派现（元）**，
    故换算为每股时统一除以 10。
    """
    fh = rd(code, "fhps")
    out = {"n": 0, "per_share": 0.0, "last_date": "—"}
    if fh is None or not len(fh):
        return out
    fh = fh.copy()
    dcol = next((c for c in ("报告期", "股权登记日", "除权除息日", "实施方案公告日期",
                             "报告时间", "最新公告日期") if c in fh.columns), None)
    if dcol is None:
        return out
    fh[dcol] = pd.to_datetime(fh[dcol], errors="coerce")
    pcol = next((c for c in ("现金分红-现金分红比例", "派息比例") if c in fh.columns), None)
    if pcol:
        fh[pcol] = pd.to_numeric(fh[pcol], errors="coerce")
    prog = fh.get("方案进度", pd.Series("", index=fh.index)).astype(str)
    sel = fh[(fh[dcol] >= pd.Timestamp("2022-01-01")) &
             (prog.str.contains("实施", na=False) | ~prog.str.contains("预案|取消", na=False))]
    out["n"] = int(len(sel))
    if pcol and len(sel):
        # 每 10 股派现（元）→ 每股（元）
        out["per_share"] = float(sel[pcol].sum()) / 10.0
        out["last_date"] = str(sel[dcol].max())[:10]
    return out


# ------------------------------------------------------------------ 行业相关度
HOG_SENSITIVE = {"生猪养殖", "肉鸡养殖", "其他养殖", "畜禽饲料", "水产饲料", "动物保健Ⅲ",
                 "动物保健", "其他农产品加工", "粮油加工"}

INDUSTRY_CYCLE_TEXT = {
    "生猪养殖": "第 \\ref{sec:hog} 章把 2026 年三季度的猪周期定位为“产能去化未完成、价格磨底”，"
              "但第 \\ref{sec:corr} 章的检验显示：生猪养殖股与猪价的月度收益率相关性并不显著"
              "（$-0.15$），领先滞后主峰在样本内也不稳定，因此估值修复的时点不能由猪价拐点直接推断。",
    "肉鸡养殖": "第 \\ref{sec:other-livestock} 章指出禽链的产能周期只有 6---12 个月、反转快于生猪，"
              "毛鸡养殖利润在 2026 年前四个月同比大增，肉鸡养殖股的报表修复在 2026 年年报中即可确认。",
    "其他养殖": "其他养殖（肉牛、肉羊、水产等）的产能周期长于生猪，"
              "第 \\ref{sec:other-livestock} 章判断肉牛供给收缩要等到 2027 年之后才兑现，"
              "相关公司的股价弹性滞后于猪周期。",
    "畜禽饲料": "饲料处于成本与需求之间（第 \\ref{sec:feed} 节），"
              "其景气同时取决于养殖存栏量（量）与原料价格差（利）；"
              "第 \\ref{sec:corr} 章的检验显示畜禽饲料指数与猪价的月度相关性并不显著（$-0.13$）。",
    "水产饲料": "水产饲料的需求取决于水产投苗量，"
              "第 \\ref{sec:other-livestock} 章显示 2026 年淡水鱼价格与投苗量已率先回升，"
              "其价格驱动与生猪存栏的联系弱于畜禽饲料（该三级行业指数未纳入第 \\ref{sec:corr} 章的相关性检验）。",
    "动物保健Ⅲ": "动保的需求由存栏量而非价格决定（第 \\ref{sec:vet} 节），"
                "在下行周期中龙头养殖企业逆势扩产反而推升疫苗需求，"
                "这解释了动保股价与猪价“脱钩”的特征。",
    "动物保健": "动保的需求由存栏量而非价格决定（第 \\ref{sec:vet} 节），"
              "在下行周期中龙头养殖企业逆势扩产反而推升疫苗需求。",
}

DEFAULT_CYCLE_TEXT = (
    "该子行业的周期来源与猪周期不同（第 \\ref{sec:grain} 章至第 \\ref{sec:soft} 章），"
    "其价格更多由自身的供给周期、进口政策与全球定价决定，因此股价与生猪价格的同步性有限。")


def short_addr(addr: str) -> str:
    s = str(addr or "")
    m = re.search(r"^(.*?(?:省|自治区|特别行政区))?(.{2,8}?市)", s)
    if m:
        return (m.group(1) or "") + m.group(2)
    return s[:12]


# ------------------------------------------------------------------ 逐公司指标
_INDEX_CACHE: dict[str, pd.Series] = {}


def index_series(name: str) -> pd.Series:
    if name not in _INDEX_CACHE:
        _INDEX_CACHE[name] = load_index_dat(name)
    return _INDEX_CACHE[name]


def analyze(code: str, name: str, meta: dict) -> dict | None:
    """汇总一家公司的画像指标。数据不足时返回 None。"""
    px = monthly_close(code)
    if px is None or len(px) < 12:
        return None

    rec: dict = {"代码": code, "名称": name, **meta}
    rec["px"] = px

    # ---------- 行情 ----------
    p0, p1 = float(px.iloc[0]), float(px.iloc[-1])
    rec.update({"起月": px.index[0], "终月": px.index[-1], "起价": p0, "终价": p1,
                "区间涨跌": (p1 / p0 - 1) * 100 if p0 else np.nan})
    rec["高"] = float(px.max())
    rec["高月"] = px.idxmax()
    rec["低"] = float(px.min())
    rec["低月"] = px.idxmin()
    lr = logret(px)
    rec["年化波动"] = float(lr.std() * np.sqrt(12) * 100) if len(lr) > 6 else np.nan

    # ---------- 周期（ZigZag） ----------
    legs = zigzag_legs(px)
    rec["legs"] = legs
    up = legs[legs["方向"] == "上涨"] if len(legs) else legs
    dn = legs[legs["方向"] == "下跌"] if len(legs) else legs
    rec["nup"], rec["ndn"] = len(up), len(dn)
    if len(up):
        i = up["幅度"].idxmax()
        rec["最大涨"] = up.loc[i]
    if len(dn):
        i = dn["幅度"].idxmin()
        rec["最大跌"] = dn.loc[i]
    rec["末段"] = legs.iloc[-1] if len(legs) else None

    # ---------- 相关度 ----------
    rec["rho_ind"] = corr_monthly(px, index_series("sw_m_801010.dat"))
    rec["rho_hog"] = corr_monthly(px, index_series("hog_spot_monthly.dat")) \
        if meta.get("三级") in HOG_SENSITIVE else np.nan

    # ---------- 财务 ----------
    fa = rd(code, "fin_abstract")
    fi = rd(code, "fin_ind")
    periods = [f"{y}1231" for y in YEARS] + [H1, H1_PREV]
    for key, metric in [("营收", "营业总收入"), ("归母", "归母净利润"),
                        ("毛利率", "毛利率"), ("净利率", "销售净利率"),
                        ("ROE", "净资产收益率(ROE)"), ("负债率", "资产负债率"),
                        ("现金流", "经营现金流量净额"), ("商誉", "商誉"),
                        ("净资产", "股东权益合计(净资产)")]:
        rec[key] = metrics_of(fa, metric, periods)
    # 财务指标表（fin_ind）：优先取 2026 年半年报（6 月末），缺失时回退 2025 年年报
    def fin_pref(col: str) -> float:
        v = fin_ind_val(fi, col, "2026-06-30")
        return v if np.isfinite(v) else fin_ind_val(fi, col, "2025-12-31")

    rec["流动比率"] = fin_pref("流动比率")
    rec["速动比率"] = fin_pref("速动比率")
    rec["存货天数"] = fin_pref("存货周转天数")
    rec["应收天数"] = fin_pref("应收账款周转天数")
    rec["总资产"] = fin_pref("总资产(元)")

    def g(key: str, period: str) -> float:
        return rec.get(key, {}).get(period, np.nan)

    rec["营收亿"] = {p: g("营收", p) / 1e8 for p in periods}
    rec["归母亿"] = {p: g("归母", p) / 1e8 for p in periods}
    rec["现金流亿"] = {p: g("现金流", p) / 1e8 for p in periods}
    # 净资产与商誉：优先 2026 年半年报，缺失时回退 2025 年年报
    for key in ("净资产", "商誉"):
        v = g(key, H1)
        rec[f"{key}期"] = H1 if np.isfinite(v) else "20251231"
    rec["净资产亿"] = g("净资产", rec["净资产期"]) / 1e8
    rec["商誉亿"] = g("商誉", rec["商誉期"]) / 1e8

    # ---------- 公告、股本、分红、主营构成 ----------
    rec["events"] = events_of(code)
    rec["share"] = share_history(code)
    rec["div"] = dividend_history(code)
    rec["comp"] = composition(code)

    # ---------- 偿债与融资（资产负债表 / 现金流量表口径） ----------
    rec["债务"] = debt_metrics(code)

    def _scale(key: str, div: float = 1e8) -> dict:
        return {d: (rec["债务"][d].get(key, np.nan) / div
                    if np.isfinite(rec["债务"][d].get(key, np.nan)) else np.nan)
                for d in FIN_DATES}

    rec["货币资金亿"] = _scale("货币资金")
    rec["有息负债亿"] = _scale("有息负债")
    rec["短期债务亿"] = _scale("短期债务")
    rec["长期债务亿"] = _scale("长期债务")
    rec["净有息负债亿"] = _scale("净有息负债")
    rec["现金短债比"] = {d: rec["债务"][d].get("现金短债比", np.nan) for d in FIN_DATES}
    rec["取得借款亿"] = _scale("取得借款")
    rec["偿还债务亿"] = _scale("偿还债务")
    rec["吸收投资亿"] = _scale("吸收投资")
    rec["筹资净额亿"] = _scale("筹资净额")
    rec["利息支付亿"] = _scale("利息支付")
    rec["购建支出亿"] = _scale("购建支出")
    rec["在建工程亿"] = _scale("在建工程")
    rec["生产性生物资产亿"] = _scale("生产性生物资产")
    rec["fin"] = fin_chart_series(rec)
    return rec


# ------------------------------------------------------------------ LaTeX 输出
GROUPS: dict[str, list[str]] = {
    "planting": ["种子", "粮食种植", "其他种植业", "食用菌"],
    "breeding": ["生猪养殖", "肉鸡养殖", "其他养殖"],
    "feed": ["畜禽饲料", "水产饲料"],
    "vet": ["动物保健Ⅲ", "动物保健"],
    "processing": ["粮油加工", "果蔬加工", "其他农产品加工"],
    "fishery": ["水产养殖", "海洋捕捞", "林业Ⅲ", "宠物食品"],
    "misc": ["农业综合Ⅱ"],
}
L2_FALLBACK = {"种植业": "planting", "养殖业": "breeding", "饲料": "feed",
               "动物保健Ⅱ": "vet", "农产品加工": "processing", "渔业": "fishery",
               "林业Ⅱ": "fishery", "农业综合Ⅱ": "misc"}


def group_of(r: dict) -> str:
    for g, inds in GROUPS.items():
        if (r.get("三级") or "") in inds:
            return g
    return L2_FALLBACK.get(r.get("二级") or "", "misc")


# ------------------------------------------------------------------ 画像上下文
# 每家公司的正文参数：行业排名、全样本中位数、周期定位、融资需求分层、
# 与行业指数见底时间的时滞。company_text 依这些参数撰写正文。
import random  # noqa: E402

import company_text as CT  # noqa: E402

# 行业周期定位（以各章结论为基础；{tail} 处补入该公司自身的读数）
CYCLE_NOTE = {
    "生猪养殖": "生猪养殖的定价主线是产能去化与成本曲线的赛跑（第 \\ref{sec:hog} 章）："
              "2026 年三季度行业仍处在“产能去化未完成、价格磨底”的阶段，{tail}",
    "肉鸡养殖": "禽链的产能周期只有 6---12 个月、反转快于生猪（第 \\ref{sec:other-livestock} 节），"
              "2026 年前四个月毛鸡养殖利润同比大幅回升，链条利润的修复先于生猪，{tail}",
    "其他养殖": "牛、羊、水产的产能周期长于生猪，第 \\ref{sec:other-livestock} 章判断肉牛供给的"
              "实质性收缩要到 2027 年之后才能兑现，这一时滞决定了个股的股价弹性，{tail}",
    "畜禽饲料": "饲料夹在原料成本与养殖需求之间（第 \\ref{sec:feed} 节），"
              "量的部分取决于存栏、利的部分取决于原料与成品的价差，{tail}",
    "水产饲料": "水产饲料的需求取决于投苗量与存塘鱼价，第 \\ref{sec:other-livestock} 章显示"
              "2026 年淡水鱼价格与投苗量已率先回升，其需求驱动与生猪存栏的联系弱于畜禽饲料，{tail}",
    "动物保健Ⅲ": "动保的需求由存栏量而非价格决定（第 \\ref{sec:vet} 节）："
                "猪价下行阶段龙头养殖企业的逆势扩产反而推升了疫苗与兽药需求，"
                "这正是动保股价与猪价“脱钩”的原因，{tail}",
    "动物保健": "动保的需求由存栏量而非价格决定（第 \\ref{sec:vet} 节）："
              "下游养殖企业的存栏规模而非盈利水平决定其收入，{tail}",
    "种子": "种子行业的价格由制种成本、粮价与政策（转基因商业化、种业振兴）共同决定"
           "（第 \\ref{sec:planting} 节），与生猪价格的联动有限，{tail}",
    "粮食种植": "土地经营型企业的收入与地租成本高度相关（第 \\ref{sec:planting} 节），"
              "粮价与政策补贴是其主要变量，{tail}",
    "其他种植业": "该子行业的周期来源与猪周期不同（第 \\ref{sec:grain} 章、第 \\ref{sec:soft} 章），"
                "价格更多由自身供给、进口政策与全球定价决定，{tail}",
    "食用菌": "食用菌是工厂化生产的制造型农业（第 \\ref{sec:soft} 章），"
            "产能投放节奏与金针菇等单品价格是盈利的主要变量，与养殖周期基本无关，{tail}",
    "粮油加工": "粮油加工是“成本加成”型生意（第 \\ref{sec:grain} 章），"
              "利润来自原料与成品的价差及规模效率，收入规模大而净利率薄，{tail}",
    "果蔬加工": "果蔬加工的外向型特征明显，出口订单与原料产地价格决定利润率，{tail}",
    "其他农产品加工": "该子行业横跨糖、番茄制品、添加剂等多个品种，"
                    "各自的供给周期与政策（进口配额、关税）是主要变量，{tail}",
    "水产养殖": "水产养殖的价格周期由投苗量与消费需求共同决定（第 \\ref{sec:other-livestock} 节），"
              "与猪周期的同步性弱于禽链，{tail}",
    "海洋捕捞": "远洋与近海捕捞的产量受资源与配额约束，成本端则跟随燃油与人工，{tail}",
    "林业Ⅲ": "林业的现金流依赖林木采伐与政策补贴，周期长、变现慢，{tail}",
    "宠物食品": "宠物食品属于消费型农业（第 \\ref{sec:financing-strategy} 节归入“向消费端延伸”），"
              "收入增长由宠物数量与单宠消费驱动，与农产品价格周期的联动最弱，{tail}",
    "农业综合Ⅱ": "农业综合类公司业务分散，估值更多取决于资产与转型预期而非单一品种价格，{tail}",
    "农产品加工": "农产品加工的价格由原料与成品价差决定，{tail}",
}


def _fin(r: dict, key: str, period: str) -> float:
    d = r.get(key)
    return d.get(period, np.nan) if isinstance(d, dict) else np.nan


def _median(vals) -> float:
    v = [float(x) for x in vals if x is not None and np.isfinite(float(x))]
    return float(np.median(v)) if v else float("nan")


def _rank(group: list[dict], r: dict, getter, higher_better: bool = True) -> int | None:
    vals = []
    for x in group:
        v = getter(x)
        if v is not None and np.isfinite(float(v)):
            vals.append((x, float(v)))
    if not vals:
        return None
    vals.sort(key=lambda t: -t[1] if higher_better else t[1])
    for i, (x, _) in enumerate(vals, 1):
        if x is r:
            return i
    return None


def _period_cn(p: str) -> str:
    p = str(p or "")
    if p.endswith("-06-30"):
        return f"{p[:4]} 年半年报"
    if p.endswith("-12-31"):
        return f"{p[:4]} 年年报"
    return "2026 年半年报"


def _index_low_month():
    """样本窗口（2021 年 1 月起）内申万农林牧渔指数的最低点月份，用于比较个股见底先后。"""
    s = index_series("sw_m_801010.dat")
    if s is None or len(s) < 12:
        return None
    s = s[s.index >= pd.Timestamp("2021-01-01")]
    if not len(s):
        return None
    return pd.Timestamp(s.idxmin())


def classify_tier(r: dict) -> int:
    """融资需求分层（与第 14 章表 14-4 的口径一致）。"""
    debt = _fin(r, "负债率", H1)
    ni = _fin(r, "归母亿", H1)
    roe = _fin(r, "ROE", H1)
    n_reorg = r["events"]["ev"].get("重大重组与并购", 0)
    if np.isfinite(ni) and ni < 0 and np.isfinite(debt) and debt > 65:
        return 1
    if n_reorg >= 10:
        return 2
    if np.isfinite(roe) and roe > 5 and np.isfinite(debt) and debt < 65:
        return 3
    return 0


def build_contexts(recs: list[dict], dossiers: dict) -> None:
    """为每家公司计算正文参数，写入 rec["ctx"]。"""
    med = {
        "roe": _median([_fin(r, "ROE", H1) for r in recs]),
        "debt": _median([_fin(r, "负债率", H1) for r in recs]),
        "vol": _median([r.get("年化波动") for r in recs]),
        "yoy": _median([r.get("近一年涨跌%") for r in recs]),
        "cap": _median([r.get("流通市值亿元") for r in recs]),
        "csr": _median([_fin(r, "现金短债比", H1) for r in recs]),
    }
    by_ind: dict[str, list[dict]] = {}
    for r in recs:
        by_ind.setdefault((r.get("三级") or r.get("二级") or "其他"), []).append(r)
    idx_trough = _index_low_month()

    for r in recs:
        code = r["代码"]
        d = dossiers.get(code) or CF.Dossier(code=code, name=r.get("名称", ""))
        R = random.Random(int(code))
        ind = r.get("三级") or r.get("二级") or "其他"
        group = by_ind.get(ind, [r])
        debt = _fin(r, "负债率", H1)
        roe = _fin(r, "ROE", H1)
        ni = _fin(r, "归母亿", H1)
        # 公司自身的周期补语（同行业的不同公司写成不同的句子）
        if np.isfinite(debt) and debt > 65:
            tail = (f"公司 2026 年 6 月末资产负债率 {debt:.1f}\\%，"
                    f"高于全样本中位数 {med['debt']:.1f}\\%，"
                    f"其股价因此更多反映资金面与信用风险，而不是价格弹性本身。")
        elif np.isfinite(roe) and np.isfinite(med.get("roe", np.nan)) and roe > med["roe"] \
                and np.isfinite(ni) and ni > 0:
            tail = (f"公司 2026 年上半年实现盈利、半年 ROE {roe:.1f}\\%（未年化），"
                    f"好于全样本中位数（{med['roe']:.2f}\\%），下行周期对其报表的冲击小于同业。")
        else:
            tail = (f"公司 2026 年 6 月末资产负债率 {CT.num_txt(debt, 1)}\\%、"
                    f"半年 ROE {CT.num_txt(roe, 1)}\\%（未年化），"
                    f"在本轮下行中属于随行业同步调整的一类。")
        # 与行业指数见底的时滞（正的月份数＝个股比板块更晚见底）
        lag = None
        if idx_trough is not None and r.get("低月") is not None:
            lag = int(round((pd.Timestamp(r["低月"]) - idx_trough).days / 30.44))
        # 三级行业同口径的 ROE 中位数：正文里“行业同口径”一句必须用这个，
        # 不能拿全样本中位数冒充行业值（两者在生猪养殖等重灾行业差别很大）
        _roes = pd.Series([x["ROE"].get(H1) for x in group], dtype="float64").dropna()
        r["ctx"] = {
            "rng": R,
            "med": med,
            "med_ind_roe": float(_roes.median()) if len(_roes) else float("nan"),
            "arch": CT.archetype(r, d),
            "tier": classify_tier(r),
            "n_ind": len(group),
            "rank_cap": _rank(group, r, lambda x: x.get("流通市值亿元")),
            "rank_roe": _rank(group, r, lambda x: _fin(x, "ROE", H1)),
            "rank_debt": _rank(group, r, lambda x: _fin(x, "负债率", H1), higher_better=False),
            "rank_vol": _rank(group, r, lambda x: x.get("年化波动")),
            "comp_period": _period_cn(((r.get("comp") or {}).get("期")) or "2026-06-30"),
            "zz": ZZ_PCT,
            "cycle_note": CYCLE_NOTE.get(ind, CYCLE_NOTE["其他种植业"]).replace("{tail}", tail),
            "lag_vs_index": lag,
        }


# ------------------------------------------------------------------ LaTeX 输出
def _w(vals) -> str:
    """缺失值写 nan（pgfplots 跳过该点），避免把缺失画成 0。"""
    out = []
    for v in vals:
        try:
            f = float(v)
            out.append("nan" if not np.isfinite(f) else f"{f:.4f}")
        except (TypeError, ValueError):
            out.append("nan")
    return " ".join(out)


def write_dat(r: dict) -> None:
    px = r["px"]
    code = r["代码"]
    with open(os.path.join(PROF, f"px_{code}.dat"), "w", encoding="utf-8") as fh:
        fh.write("x y\n")
        for d, v in px.items():
            fh.write(f"{dec_year(d):.4f} {float(v):.4f}\n")
    kept = zigzag_kept(px)
    with open(os.path.join(PROF, f"pxzz_{code}.dat"), "w", encoding="utf-8") as fh:
        fh.write("x y\n")
        for d, v in kept:
            fh.write(f"{dec_year(pd.Timestamp(d)):.4f} {float(v):.4f}\n")

    # 近年主要财务指标（年报 2021---2025）
    fin = r.get("fin") or {}
    ann = fin.get("annual") or {}
    years = sorted(ann.keys())
    with open(os.path.join(PROF, f"fin_{code}.dat"), "w", encoding="utf-8") as fh:
        fh.write("i rev ni roe debt cash ibd ocf\n")
        for i, y in enumerate(years):
            a = ann[y]
            fh.write(f"{i} " + _w([a.get("rev"), a.get("ni"), a.get("roe"),
                                   a.get("debt"), a.get("cash"), a.get("ibd"),
                                   a.get("ocf")]) + "\n")
    # 2026 年半年报（横轴留出间隔：x = 5.7）
    h1 = fin.get("h1") or {}
    with open(os.path.join(PROF, f"finh_{code}.dat"), "w", encoding="utf-8") as fh:
        fh.write("x rev ni roe debt cash ibd ocf\n")
        fh.write("5.7 " + _w([h1.get("rev"), h1.get("ni"), h1.get("roe"),
                              h1.get("debt"), h1.get("cash"), h1.get("ibd"),
                              h1.get("ocf")]) + "\n")


def csv_row(r: dict) -> dict:
    ev = r["events"]["ev"]
    sh = r["share"]
    dv = r["div"]
    c = r.get("comp") or {}
    return {
        "代码": r["代码"], "名称": r["名称"], "一级": r.get("一级"), "二级": r.get("二级"),
        "三级": r["三级"], "上市日期": r.get("上市日期"), "市场": r.get("所属市场"),
        "注册地": r.get("省市"), "注册资本万元": r.get("注册资本"),
        "主营": r.get("主营"),
        "最新收盘": r.get("最新收盘"), "行情日期": r.get("行情日期"),
        "流通市值亿元": r.get("流通市值亿元"), "近一年涨跌%": r.get("近一年涨跌%"),
        "总股本亿股": r.get("总股本亿股"),
        "样本起月": str(r["起月"])[:7], "样本终月": str(r["终月"])[:7],
        "区间涨跌%": r["区间涨跌"], "区间最高": r["高"], "最高月": str(r["高月"])[:7],
        "区间最低": r["低"], "最低月": str(r["低月"])[:7], "年化波动%": r.get("年化波动"),
        "主升段数": r["nup"], "主跌段数": r["ndn"],
        "最大主升%": r["最大涨"]["幅度"] if "最大涨" in r else np.nan,
        "最大主跌%": r["最大跌"]["幅度"] if "最大跌" in r else np.nan,
        "末段方向": r["末段"]["方向"] if r.get("末段") is not None else "",
        "末段起": str(r["末段"]["起"])[:7] if r.get("末段") is not None else "",
        "末段幅度%": r["末段"]["幅度"] if r.get("末段") is not None else np.nan,
        "与行业指数相关": r.get("rho_ind"), "与猪价指数相关": r.get("rho_hog"),
        "营收2023亿": r["营收亿"].get("20231231"), "营收2024亿": r["营收亿"].get("20241231"),
        "营收2025亿": r["营收亿"].get("20251231"), "营收2026H1亿": r["营收亿"].get(H1),
        "营收2026H1同比%": (r["营收亿"][H1] / r["营收亿"][H1_PREV] - 1) * 100
        if np.isfinite(r["营收亿"].get(H1, np.nan)) and np.isfinite(r["营收亿"].get(H1_PREV, np.nan))
        and r["营收亿"].get(H1_PREV, 0) not in (0,) else np.nan,
        "归母2023亿": r["归母亿"].get("20231231"), "归母2024亿": r["归母亿"].get("20241231"),
        "归母2025亿": r["归母亿"].get("20251231"), "归母2026H1亿": r["归母亿"].get(H1),
        "归母2025H1亿": r["归母亿"].get(H1_PREV),
        "ROE2025": r["ROE"].get("20251231"), "毛利率2025": r["毛利率"].get("20251231"),
        "净利率2025": r["净利率"].get("20251231"),
        "负债率2023": r["负债率"].get("20231231"), "负债率2024": r["负债率"].get("20241231"),
        "负债率2025": r["负债率"].get("20251231"), "负债率2026H1": r["负债率"].get(H1),
        "现金流2025亿": r["现金流亿"].get("20251231"),
        "ROE2026H1": r["ROE"].get(H1), "毛利率2026H1": r["毛利率"].get(H1),
        "净利率2026H1": r["净利率"].get(H1), "现金流2026H1亿": r["现金流亿"].get(H1),
        "净资产亿": r.get("净资产亿"), "净资产期": r.get("净资产期"),
        "流动比率": r.get("流动比率"), "速动比率": r.get("速动比率"),
        "存货周转天数": r.get("存货天数"), "应收周转天数": r.get("应收天数"),
        "商誉亿": r.get("商誉亿"),
        **{f"公告-{k}": v for k, v in ev.items()},
        "近三年公告数": r["events"]["n"],
        "股本变动次数2023+": sh["n2023"], "股本变动原因": sh["reasons"],
        "最近股本变动": str(sh["last"])[:10],
        "总股本2021亿股": sh.get("first_total"), "总股本最新亿股": sh.get("last_total"),
        "增发次数": sh.get("raise"), "可转债转股次数": sh.get("cb"),
        "近三年分红次数": dv["n"], "近三年每股分红": dv["per_share"],
        "主营构成期": c.get("期"), "主营构成类别": c.get("类别"),
        "主营首位": c["新"][0][0] if c.get("ok") and c["新"] else "",
        "主营首位占比": c["新"][0][1] if c.get("ok") and c["新"] else np.nan,
        "主营首位2021": c["旧"][0][0] if c.get("old_ok") or c.get("旧") else "",
        "主营首位变化": c.get("首位变化"), "主营首位占比变化": c.get("首位占比变化"),
        "画像": group_of(r),
        # 偿债与融资结构（2026 年半年报口径）
        "货币资金2026H1亿": r["货币资金亿"].get(H1),
        "短期债务2026H1亿": r["短期债务亿"].get(H1),
        "有息负债2026H1亿": r["有息负债亿"].get(H1),
        "现金短债比2026H1": r["现金短债比"].get(H1),
        "取得借款2025亿": r["取得借款亿"].get("20251231"),
        "偿还债务2025亿": r["偿还债务亿"].get("20251231"),
        "筹资净额2025亿": r["筹资净额亿"].get("20251231"),
        "取得借款2026H1亿": r["取得借款亿"].get(H1),
        "偿还债务2026H1亿": r["偿还债务亿"].get(H1),
        "在建工程2026H1亿": r["在建工程亿"].get(H1),
        # 画像口径：融资需求分层与事实底稿覆盖
        "融资需求分层": (r.get("ctx") or {}).get("tier"),
        "公司类型": (r.get("ctx") or {}).get("arch"),
        "事实底稿条目": len(r.get("facts_items", [])),
        "融资历史条目": len(r.get("facts_fin", [])),
    }


def main() -> None:
    uni = pd.read_csv(os.path.join(CLEAN, "sw_stock_industry.csv"),
                      encoding="utf-8-sig", dtype=str)
    l1 = uni[uni["行业层级"] == "一级"][["股票代码", "证券名称"]].drop_duplicates("股票代码")
    master = pd.read_csv(os.path.join(CLEAN, "company_master.csv"),
                         encoding="utf-8-sig", dtype=str).set_index("代码")

    def level(code: str, lv: str) -> str:
        s = uni[(uni["股票代码"] == code) & (uni["行业层级"] == lv)]
        return s["行业名称"].iloc[0] if len(s) else ""

    log(f"# 农业上市公司画像（逐公司）\n\n样本：申万农林牧渔一级行业 {len(l1)} 家公司\n")
    recs, skipped = [], []
    for _, row in l1.iterrows():
        code = str(row["股票代码"]).zfill(6)
        name = str(row["证券名称"])
        m = master.loc[code] if code in master.index else None
        meta = {"一级": level(code, "一级"), "二级": level(code, "二级"),
                "三级": level(code, "三级")}
        zj = rd(code, "zyjs")
        if zj is not None and len(zj) and "主营业务" in zj.columns:
            v = str(zj["主营业务"].iloc[0]).strip()
            if v and v.lower() != "nan":
                meta["主营"] = v[:80]
        if m is not None:
            meta.update({
                "上市日期": str(m.get("上市日期", ""))[:10],
                "所属市场": m.get("所属市场", ""),
                "省市": short_addr(m.get("注册地", "")),
                "注册资本": num(m.get("注册资本万元", np.nan)),
                "主营": meta.get("主营") or str(m.get("主营业务", "") or ""),
                "最新收盘": num(m.get("最新收盘", np.nan)),
                "行情日期": str(m.get("行情日期", ""))[:10],
                "流通市值亿元": num(m.get("流通市值亿元", np.nan)),
                "近一年涨跌%": num(m.get("近一年涨跌%", np.nan)),
                "总股本亿股": num(m.get("总股本亿股", np.nan)),
            })
        r = analyze(code, name, meta)
        if r is None:
            skipped.append((code, name))
            continue
        recs.append(r)

    recs.sort(key=lambda x: -(x.get("流通市值亿元") if np.isfinite(
        x.get("流通市值亿元", np.nan)) else 0))
    log(f"成功生成 {len(recs)} 家，跳过 {len(skipped)} 家：{skipped}\n")

    # ---- 事实底稿（data/facts/*.yaml）：逐公司画像的叙述来源 ----
    dossiers = CF.load_all()
    for r in recs:
        d = dossiers.get(r["代码"])
        r["facts_items"] = d.items if d else []
        r["facts_fin"] = d.融资历史 if d else []
    with_facts = sum(1 for r in recs if r["facts_items"])
    log(f"\n## 事实底稿\n")
    log(f"- 有底稿的公司：{with_facts}/{len(recs)} 家")
    log(f"- 有融资历史条目：{sum(1 for r in recs if r['facts_fin'])} 家；"
        f"条目合计 {sum(len(r['facts_fin']) for r in recs)} 条")
    probs = CF.validate(dossiers)
    log(f"- 底稿结构校验问题：{len(probs)} 条")
    for p in probs[:20]:
        log(f"    - {p}")
    build_contexts(recs, dossiers)
    tiers = {t: sum(1 for r in recs if r["ctx"]["tier"] == t) for t in (0, 1, 2, 3)}
    log(f"- 融资需求分层：第一档 {tiers[1]} 家、第二档 {tiers[2]} 家、"
        f"第三档 {tiers[3]} 家、其他 {tiers[0]} 家\n")

    # ---- 逐家数据文件 ----
    for r in recs:
        write_dat(r)

    # ---- LaTeX 片段 ----
    for g, inds in GROUPS.items():
        sub = [r for r in recs if group_of(r) == g]
        if not sub:
            continue
        out = [f"% 农业上市公司画像：{'、'.join(inds)}（共 {len(sub)} 家，按流通市值降序）",
               f"% 由 scripts/make_company_profiles.py 自动生成，请勿手工修改", ""]
        for r in sub:
            d = dossiers.get(r["代码"]) or CF.Dossier(code=r["代码"], name=r["名称"])
            out.append(CT.tex_company(r, d, r["ctx"]))
        with open(os.path.join(GEN, f"{g}.tex"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        log(f"- {g}: {len(sub)} 家")

    # ---- 汇总 CSV ----
    df = pd.DataFrame([csv_row(r) for r in recs])
    # 申万“农业综合Ⅱ”等成分股没有三级行业，回退到二级行业，避免表格出现空单元格
    for c in ("三级", "二级", "一级"):
        if c in df.columns:
            df[c] = df[c].fillna("").replace("", np.nan)
    df["三级"] = df["三级"].fillna(df["二级"]).fillna(df["一级"]).fillna("未分类")
    df.to_csv(os.path.join(CLEAN, "company_profiles.csv"), index=False, encoding="utf-8-sig")

    # ---- 2026 年半年报 vs 上年同期的盈利分布（供第二部分总览作图） ----
    bins = [-1e9, -5, -1, 0, 1, 5, 1e9]
    labels = ["<-5", "-5~-1", "-1~0", "0~1", "1~5", ">5"]
    dist = {}
    for key, col in (("2025H1", "归母2025H1亿"), ("2026H1", "归母2026H1亿")):
        s = pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
        dist[key] = pd.cut(s, bins=bins, labels=labels).value_counts().reindex(labels).fillna(0)
    with open(os.path.join(CLEAN, "comp_h1_dist.dat"), "w", encoding="utf-8") as fh:
        fh.write("i a b label\n")
        for i, lb in enumerate(labels):
            fh.write(f"{i} {int(dist['2025H1'][lb])} {int(dist['2026H1'][lb])} {lb}\n")

    # ---- 2026 年半年报概览表：已并入附录 B 的画像总表（company_master.tex），不再单独出表 ----

    # ---- 债务结构与滚动偿付压力总表（附录 B，供第 14 章引用） ----
    def _f(r_, key, period=H1):
        d = r_.get(key)
        v = d.get(period, np.nan) if isinstance(d, dict) else np.nan
        try:
            return float(v)
        except (TypeError, ValueError):
            return np.nan

    def _s(v, nd=2):
        return "---" if not np.isfinite(v) else f"{v:,.{nd}f}"

    tier_cn = {1: "第一档", 2: "第二档", 3: "第三档", 0: "---"}
    frows = []
    for r in recs:
        cash, sd = _f(r, "货币资金亿"), _f(r, "短期债务亿")
        frows.append((r, cash, sd, _f(r, "有息负债亿"), _f(r, "现金短债比"),
                      sd - cash if np.isfinite(sd) and np.isfinite(cash) else np.nan,
                      tier_cn.get(r["ctx"]["tier"], "---")))
    frows.sort(key=lambda t: (np.inf if not np.isfinite(t[4]) else t[4]))
    fcols = ["代码", "公司简称", "申万三级行业", "货币资金", "短期债务", "有息负债",
             "现金短债比", "静态缺口", "融资需求档"]
    assert len(fcols) == 9, f"附录债务压力表列数应为 9，实际 {len(fcols)}"
    fout = [r"\begingroup\scriptsize\setlength{\tabcolsep}{1.5pt}",
            r"\begin{longtable}{@{}llp{1.9cm}rrrrrl@{}}",
            r"\caption{农业上市公司债务结构与滚动偿付压力（2026 年 6 月末；按现金短债比升序；"
            r"单位：亿元，现金短债比为倍）}\label{tab:company-financing}\\",
            r"\toprule", " & ".join(fcols) + r" \\", r"\midrule", r"\endfirsthead",
            r"\multicolumn{9}{l}{\small（续）}\\", r"\toprule",
            " & ".join(fcols) + r" \\", r"\midrule", r"\endhead",
            r"\bottomrule", r"\endlastfoot"]
    for r, cash, sd, ibd, csr, gap, tier in frows:
        cells = [r["代码"], tex_escape(r["名称"]), tex_escape(r.get("三级") or "---"),
                 _s(cash), _s(sd), _s(ibd),
                 "---" if not np.isfinite(csr) else f"{csr:,.2f}",
                 "---" if not np.isfinite(gap) else f"{gap:,.2f}", tier]
        fout.append(" & ".join(cells) + r" \\")
    fout += [r"\end{longtable}", r"\endgroup"]
    # 注意：GEN 指向 tex/gen/profiles（逐公司片段），这张汇总表要放在 tex/gen/ 下
    with open(os.path.join(GENROOT, "company_financing.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fout) + "\n")
    neg_gap = sum(1 for t in frows if np.isfinite(t[5]) and t[5] > 0)
    log(f"- 附录表 company_financing.tex：短期债务超过货币资金的 {neg_gap} 家，"
        f"静态缺口合计 {sum(max(t[5], 0) for t in frows if np.isfinite(t[5])):,.0f} 亿元")

    # ---- 摘要 ----
    n26 = int(df["归母2026H1亿"].notna().sum()) if "归母2026H1亿" in df else 0
    log(f"\n## 覆盖情况\n")
    log(f"- 有月度行情（≥12 个月）：{len(recs)} 家")
    log(f"- 有 2026 年半年报归母净利润：{n26} 家")
    log(f"- 2025 年亏损（对照）：{int((pd.to_numeric(df['归母2025亿'], errors='coerce') < 0).sum())} 家")
    log(f"- 2026 年上半年亏损：{int((pd.to_numeric(df['归母2026H1亿'], errors='coerce') < 0).sum())} 家")
    log(f"- 资产负债率 > 65%（2026 年 6 月末）："
        f"{int((pd.to_numeric(df['负债率2026H1'], errors='coerce') > 65).sum())} 家")
    with open(os.path.join(NOTES, "company_profiles_summary.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(str(x) for x in LOG) + "\n")
    log(f"\n→ {CLEAN}/company_profiles.csv, {CLEAN}/profiles/*.dat, {GEN}/*.tex")


if __name__ == "__main__":
    main()
