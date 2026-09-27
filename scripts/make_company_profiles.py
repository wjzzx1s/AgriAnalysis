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
        out["首位变化"] = (t_new[0][0] != t_old[0][0])
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
    rec["流动比率"] = fin_ind_val(fi, "流动比率", "2025-12-31")
    rec["速动比率"] = fin_ind_val(fi, "速动比率", "2025-12-31")
    rec["存货天数"] = fin_ind_val(fi, "存货周转天数", "2025-12-31")
    rec["应收天数"] = fin_ind_val(fi, "应收账款周转天数", "2025-12-31")
    rec["总资产"] = fin_ind_val(fi, "总资产(元)", "2025-12-31")

    def g(key: str, period: str) -> float:
        return rec.get(key, {}).get(period, np.nan)

    rec["营收亿"] = {p: g("营收", p) / 1e8 for p in periods}
    rec["归母亿"] = {p: g("归母", p) / 1e8 for p in periods}
    rec["现金流亿"] = {p: g("现金流", p) / 1e8 for p in periods}
    rec["净资产亿"] = g("净资产", "20251231") / 1e8
    rec["商誉亿"] = g("商誉", "20251231") / 1e8

    # ---------- 公告、股本、分红、主营构成 ----------
    rec["events"] = events_of(code)
    rec["share"] = share_history(code)
    rec["div"] = dividend_history(code)
    rec["comp"] = composition(code)
    return rec


# ------------------------------------------------------------------ 文本生成
def para_basic(r: dict) -> str:
    meta = []
    if r.get("省市"):
        meta.append(f"注册地位于{r['省市']}")
    if r.get("上市日期"):
        meta.append(f"{r['上市日期']} 在{r.get('所属市场') or 'A 股'}上市")
    if np.isfinite(r.get("注册资本", np.nan)):
        meta.append(f"注册资本 {r['注册资本'] / 1e4:.2f} 亿元")
    s = "公司" + "，".join(meta) + "。" if meta else "公司"
    if r.get("主营"):
        s += f"主营业务为“{str(r['主营']).strip().rstrip('。；;，, ')}”。"
    s += f"按申万行业分类（2021 版）归属三级行业“{r.get('三级') or '—'}”（二级行业“{r.get('二级') or '—'}”）。"
    if np.isfinite(r.get("流通市值亿元", np.nan)):
        s += (f"截至 {r.get('行情日期', '—')}，总股本 {dash(r.get('总股本亿股'), 2)} 亿股，"
              f"收盘价 {dash(r.get('最新收盘'), 2)} 元，流通市值 {dash(r.get('流通市值亿元'), 1)} 亿元，"
              f"近一年涨跌幅 {zz(r.get('近一年涨跌%'))}。")
    c = r.get("comp") or {}
    if c.get("ok"):
        items = "；".join(f"{tex_escape(k)} {dash(v, 1, '%')}"
                           for k, v in c["新"] if np.isfinite(v))
        if items:
            s += f"按 {period_cn(c['期'])}披露的{c['类别'][1:]}，收入占比最高的三项为{items}。"
            tot = c.get("合计", np.nan)
            if np.isfinite(tot):
                s += (f"三项合计 {dash(tot, 1)}%。" if tot <= 105
                      else f"三项合计 {dash(tot, 1)}%，超过 100% 的部分来自内部销售抵消。")
    return s


def period_cn(p: str) -> str:
    """报告期 → 中文期次。"""
    p = str(p)
    if p.endswith("-06-30"):
        return f"{p[:4]} 年半年报"
    if p.endswith("-12-31"):
        return f"{p[:4]} 年年报"
    return p


def para_price(r: dict) -> str:
    s = (f"本报告样本区间（{ym(r['起月'])} 至 {ym(r['终月'])}）内，公司股价由 {r['起价']:.2f} 元"
         f"变为 {r['终价']:.2f} 元，累计 {zz(r['区间涨跌'])}；区间最高 {r['高']:.2f} 元"
         f"（{ym(r['高月'])}）、最低 {r['低']:.2f} 元（{ym(r['低月'])}）；"
         f"当前价相当于区间最高价的 {r['终价'] / r['高'] * 100:.1f}%、区间最低价的 "
         f"{r['终价'] / r['低']:.2f} 倍。")
    if np.isfinite(r.get("年化波动", np.nan)):
        s += f"月度收益的年化波动率为 {r['年化波动']:.1f}%。"
    return s


def para_cycle(r: dict) -> str:
    s = (f"以 {ZZ_PCT * 100:.0f}% 的 ZigZag 阈值划分，样本区间内股价形成 {r['nup']} 个主升段与 "
         f"{r['ndn']} 个主跌段。")
    if "最大涨" in r:
        x = r["最大涨"]
        s += (f"最大主升段出现在 {ym(x['起'])} 至 {ym(x['止'])}，{x['月数']:.0f} 个月上涨 "
              f"{zz(x['幅度'])}；")
    if "最大跌" in r:
        x = r["最大跌"]
        s += (f"最大主跌段为 {ym(x['起'])} 至 {ym(x['止'])}，{x['月数']:.0f} 个月下跌 "
              f"{zz(x['幅度'])}。")
    if r.get("末段") is not None:
        x = r["末段"]
        s += (f"最近一次转折发生在 {ym(x['止'])}（{x['方向']}段自 {ym(x['起'])}起，"
              f"{x['月数']:.0f} 个月 {zz(x['幅度'])}），当前处于该段的延续之中。")
    if np.isfinite(r.get("rho_ind", np.nan)):
        s += f"公司股价与其所属一级行业指数（申万农林牧渔）的月度收益相关系数为 {r['rho_ind']:+.2f}"
        if np.isfinite(r.get("rho_hog", np.nan)):
            s += f"，与生猪价格指数的相关系数为 {r['rho_hog']:+.2f}"
        s += "。"
    s += INDUSTRY_CYCLE_TEXT.get(r.get("三级") or "", DEFAULT_CYCLE_TEXT)
    return s


def para_profit(r: dict) -> str:
    a, b = r["营收亿"].get("20231231", np.nan), r["营收亿"].get("20251231", np.nan)
    na, nb = r["归母亿"].get("20231231", np.nan), r["归母亿"].get("20251231", np.nan)
    s = ""
    if np.isfinite(a) and np.isfinite(b) and a > 0:
        cagr = ((b / a) ** 0.5 - 1) * 100
        s += (f"2023---2025 年营业收入由 {yi(a)} 亿元变为 {yi(b)} 亿元"
              f"（两年年均复合增速 {zz(cagr)}），")
    elif np.isfinite(b):
        s += f"2025 年营业收入 {yi(b)} 亿元，"
    if np.isfinite(na) and np.isfinite(nb):
        s += f"归母净利润由 {yi(na)} 亿元变为 {yi(nb)} 亿元。"
    else:
        s += "归母净利润数据缺失。"
    e, f = r["营收亿"].get(H1, np.nan), r["归母亿"].get(H1, np.nan)
    ep, fp = r["营收亿"].get(H1_PREV, np.nan), r["归母亿"].get(H1_PREV, np.nan)
    if np.isfinite(e):
        s += f"2026 年上半年营业收入 {yi(e)} 亿元"
        if np.isfinite(ep) and ep > 0:
            s += f"（同比 {zz((e / ep - 1) * 100)}）"
        s += "，"
        if np.isfinite(f):
            s += f"归母净利润 {yi(f)} 亿元"
            if np.isfinite(fp) and abs(fp) > 1e-6:
                s += f"（同比 {zz((f / abs(fp) - 1) * 100) if fp > 0 else '由亏转盈' if f > 0 else '亏损收窄' if abs(f) < abs(fp) else '亏损扩大'}）"
            s += "。"
        else:
            s += "归母净利润数据缺失。"
    roe = r["ROE"].get("20251231", np.nan)
    npr = r["净利率"].get("20251231", np.nan)
    gpr = r["毛利率"].get("20251231", np.nan)
    extra = [f"2025 年 ROE {dash(roe, 1, '%')}", f"销售净利率 {dash(npr, 1, '%')}",
             f"毛利率 {dash(gpr, 1, '%')}"]
    s += "，".join(extra) + "。"
    # 定性
    y = nb
    h = f
    if np.isfinite(y) and y > 0 and np.isfinite(h) and h > 0:
        s += "公司 2025 年报与 2026 年半年报均实现归母净利润为正，是周期底部中盈利能力较为稳定的一类。"
    elif np.isfinite(y) and y > 0 and np.isfinite(h) and h <= 0:
        s += "公司 2025 年盈利而 2026 年上半年转亏，说明其盈利对价格变化高度敏感，下半年需观察价格与成本的相对变化。"
    elif np.isfinite(y) and y <= 0 and np.isfinite(h) and h > 0:
        s += "公司在 2026 年上半年已经扭亏，是报告样本中较早出现盈利修复的一类。"
    elif np.isfinite(y) and y <= 0 and np.isfinite(h) and h <= 0:
        if np.isfinite(fp) and abs(h) > abs(fp):
            s += "公司连续处于亏损状态且 2026 年上半年亏损同比扩大，资产负债表的修复尚未开始。"
        else:
            s += "公司连续处于亏损状态，但 2026 年上半年亏损同比收窄，属于周期底部的边际改善者。"
    return s


def para_finance(r: dict) -> str:
    d25 = r["负债率"].get("20251231", np.nan)
    d23 = r["负债率"].get("20231231", np.nan)
    s = f"2025 年末资产负债率 {dash(d25, 1, '%')}"
    if np.isfinite(d23) and np.isfinite(d25):
        ch = d25 - d23
        s += f"，较 2023 年末{'上升' if ch > 0 else '下降'} {abs(ch):.1f} 个百分点"
    s += "。"
    if np.isfinite(r.get("流动比率", np.nan)):
        s += (f"2025 年报的流动比率为 {r['流动比率']:.2f}、速动比率 {dash(r.get('速动比率'), 2)}，"
              f"{'短期偿债指标偏紧' if r['流动比率'] < 1.2 else '短期偿债指标尚可'}；")
    if np.isfinite(r.get("存货天数", np.nan)):
        s += (f"存货周转天数 {r['存货天数']:.0f} 天、应收账款周转天数 "
              f"{dash(r.get('应收天数'), 0)} 天。")
    cf = r["现金流亿"].get("20251231", np.nan)
    if np.isfinite(cf):
        s += f"2025 年经营活动现金流净额 {yi(cf)} 亿元"
        if np.isfinite(r["归母亿"].get("20251231", np.nan)):
            ni = r["归母亿"]["20251231"]
            s += "，" + ("经营现金流为正，可在不依赖外部融资的情况下维持运营。"
                         if cf > 0 and ni > 0 else
                         "经营现金流为负，日常运营对债务与股东投入的依赖度较高。"
                         if cf < 0 else
                         "经营现金流为正但净利润为负，主要是折旧摊销与营运资本变动所致。")
        else:
            s += "。"
    if np.isfinite(r.get("商誉亿", np.nan)) and r["商誉亿"] > 1:
        s += f"2025 年末商誉 {yi(r['商誉亿'])} 亿元，占净资产的 {r['商誉亿'] / r['净资产亿'] * 100:.1f}%（若存在减值风险会直接冲击净资产）。" \
            if np.isfinite(r.get("净资产亿", np.nan)) and r["净资产亿"] > 0 else \
            f"2025 年末商誉 {yi(r['商誉亿'])} 亿元。"
    return s


def para_strategy(r: dict) -> str:
    ev = r["events"]["ev"]
    c = r.get("comp") or {}
    s = (f"近三年（2023 年 9 月---2026 年 9 月）公司披露重大重组与并购类公告 {ev.get('重大重组与并购', 0)} 条、"
         f"对外投资与转型类公告 {ev.get('对外投资与转型', 0)} 条。")
    titles = r["events"]["titles"]
    pick = []
    skip_re = re.compile(r"制度|管理办法|管理规则|细则|章程|自查|说明|问询|回复")
    for k in ("重大重组与并购", "对外投资与转型"):
        for t in titles.get(k, []):
            t = re.sub(r"\s+", "", str(t))
            if skip_re.search(t) or t in pick:
                continue
            pick.append(t)
            if len(pick) >= 3:
                break
        if len(pick) >= 3:
            break
    if pick:
        s += "典型公告包括" + "、".join(f"“{tex_escape(t[:34])}”" for t in pick) + "等。"
    if c.get("ok") and c.get("旧"):
        old_top = c["旧"][0][0]
        new_top = c["新"][0][0]
        unit = "行业" if "行业" in c["类别"] else "产品"
        if c.get("首位变化"):
            s += (f"主营结构发生实质性变化：{period_cn(c['旧期'])}的第一大{unit}为“{old_top}”，"
                  f"至 {period_cn(c['期'])}已变为“{new_top}”，业务重心发生迁移。")
        elif np.isfinite(c.get("首位占比变化", np.nan)) and abs(c["首位占比变化"]) >= 12:
            s += (f"第一大{unit}“{new_top}”的收入占比由 {period_cn(c['旧期'])}的 "
                  f"{c['旧'][0][1]:.1f}% 变为 {period_cn(c['期'])}的 {c['新'][0][1]:.1f}%"
                  f"（{abs(c['首位占比变化']):.1f} 个百分点），收入结构出现明显再平衡。")
        else:
            s += (f"第一大{unit}仍为“{new_top}”，收入占比 {dash(c['新'][0][1], 1, '%')}，"
                  f"与 {period_cn(c['旧期'])}相比未发生方向性变化。")
    # 结论
    trans = (ev.get("重大重组与并购", 0) >= 5) or (ev.get("对外投资与转型", 0) >= 15) \
        or bool(c.get("首位变化")) or (np.isfinite(c.get("首位占比变化", np.nan)) and abs(c["首位占比变化"]) >= 12)
    if "ST" in str(r["名称"]):
        s += ("公司证券简称含风险警示标识，报告期内以“保壳”为主要资本运作目标，"
              "属于第 \\ref{sec:financing-strategy} 节界定的“跨界与保壳”路径。")
    elif trans:
        s += "综合判断，公司在报告期内存在明确的战略转型或外延扩张动作。"
    else:
        s += "综合判断，公司报告期内未出现实质性战略转型，主业结构保持稳定，资本运作以维持现有业务为主。"
    return s


def para_invest(r: dict) -> str:
    sh, dv = r["share"], r["div"]
    s = f"公司于 {r.get('上市日期') or '—'} 首发上市；"
    s += f"近三年披露股本变动 {sh['n2023']} 次"
    if sh["reasons"]:
        s += f"（主要原因为{sh['reasons']}）"
    s += f"，最近一次股本变动为 {str(sh['last'])[:10]}。"
    if np.isfinite(sh.get("first_total", np.nan)) and np.isfinite(sh.get("last_total", np.nan)) \
            and sh["first_total"] > 0:
        s += (f"总股本由 2021 年末的 {sh['first_total']:.2f} 亿股变为 {sh['last_total']:.2f} 亿股"
              f"（{zz((sh['last_total'] / sh['first_total'] - 1) * 100)}）。")
    if dv["n"] > 0:
        s += (f"近三年现金分红 {dv['n']} 次，累计每股派现 {dv['per_share']:.2f} 元"
              f"（最近一次为 {dv['last_date']}）。")
    else:
        s += "近三年未实施现金分红，分红能力在整体样本中处于偏弱一端。"
    nref = r["events"]["ev"].get("再融资", 0)
    s += f"近三年“再融资”类公告 {nref} 条"
    t = " ".join(r["events"]["titles"].get("再融资", []))
    kinds = []
    for pat, label in [(r"向特定对象发行", "定向增发"), (r"可转换公司债券", "可转债"),
                       (r"(?<!分)配股", "配股"),
                       (r"发行股份购买", "发行股份购买资产"),
                       (r"募集说明书", "募集说明书")]:
        if re.search(pat, t):
            kinds.append(label)
    if kinds:
        s += f"，其中涉及{('、'.join(kinds))}"
    s += "。"
    return s


def para_need(r: dict) -> str:
    d = r["负债率"].get("20251231", np.nan)
    ni = r["归母亿"].get("20251231", np.nan)
    roe = r["ROE"].get("20251231", np.nan)
    rev = r["events"]["ev"]
    loss = np.isfinite(ni) and ni < 0
    high_debt = np.isfinite(d) and d > 65
    s = ""
    if loss and high_debt:
        s = (f"按第 \\ref{{sec:financing-need}} 节的分层口径，公司属于第一档“补血型”："
             f"2025 年归母净利润 {yi(ni)} 亿元、年末资产负债率 {dash(d, 1, '%')}（高于 65% 的警戒线）。")
        if d > 80:
            s += "负债率已超过 80%，净资产被亏损侵蚀的程度较深，属于全部样本中资产负债表最紧张的一组。"
        gap = abs(ni)
        if np.isfinite(r.get("总资产", np.nan)) and np.isfinite(d):
            debt = d / 100 * r["总资产"] / 1e8
            interest = 0.6 * debt * 0.04
            gap_hi = abs(ni) + interest
            s += (f"按“补足当年亏损 + 覆盖一年利息”的粗略口径（有息负债按负债总额的 60%、"
                  f"利率 4% 估算），融资缺口约 {gap:.1f}---{gap_hi:.1f} 亿元。")
        s += ("可行的融资路径为定向增发、债务重组、出售非核心资产或引入战略投资者；"
              "由于处于亏损状态，股权融资需要股价配合，债务置换与资产处置的可行性更高。")
    elif loss and not high_debt:
        s = (f"公司 2025 年归母净利润为负（{yi(ni)} 亿元），但资产负债率 {dash(d, 1, '%')} "
             f"仍低于 65% 的警戒线，暂不属于第一档“补血型”。")
        s += ("当前融资需求以补充流动资金、支撑低谷期的经营性支出为主；"
              "若 2026 年下半年亏损延续、负债率抬升，则会向第一档迁移。")
    elif (np.isfinite(roe) and roe > 10) and np.isfinite(d) and d < 65:
        s = (f"公司 2025 年 ROE {dash(roe, 1, '%')}、资产负债率 {dash(d, 1, '%')}，"
             f"资产负债表具备进一步加杠杆的空间，属于第三档“扩张型”。")
        s += ("融资需求以产能扩张、海外布局与品类并购为主，"
              "这类融资通常被市场定价为成长而非补血，单笔规模多在 5---20 亿元量级。")
    elif high_debt:
        s = (f"公司 2025 年实现盈利但资产负债率 {dash(d, 1, '%')} 偏高，"
             f"处于“以经营现金流修复杠杆”的过渡状态。")
        s += ("潜在融资需求以债务置换与流动性补充为主，而非股权补血；"
              "若行业景气继续下行，杠杆水平会先于利润恶化。")
    else:
        s = (f"公司 2025 年资产负债率 {dash(d, 1, '%')}、ROE {dash(roe, 1, '%')}，"
             f"资产负债表稳健且盈利水平平淡，暂无刚性融资需求。")
        s += ("潜在融资需求以技改扩产、并购与被并购为主，规模取决于其扩张节奏。")
    n_reorg = rev.get("重大重组与并购", 0)
    if n_reorg >= 10:
        s += (f"公司近三年重大重组与并购类公告 {n_reorg} 条（达到 10 条门槛），"
              f"按上述分层口径属于第二档“保壳型”，融资需求更可能以“资产置换 + 保壳”的形式出现。")
    elif "ST" in str(r["名称"]):
        s += (f"公司现处 ST 状态、近三年重大重组与并购类公告 {n_reorg} 条（未达第二档的 10 条门槛），"
              f"若重组推进，融资需求更可能以“资产置换 + 保壳”的形式出现。")
    return s


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


def chart(r: dict) -> str:
    px = r["px"]
    x0, x1 = dec_year(px.index[0]), dec_year(px.index[-1])
    y0, y1 = r["低"] * 0.93, r["高"] * 1.07
    years = list(range(px.index[0].year, px.index[-1].year + 1))
    zz_path = f"data/clean/profiles/pxzz_{r['代码']}.dat"
    px_path = f"data/clean/profiles/px_{r['代码']}.dat"
    return "\n".join([
        r"\begin{center}",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=12.6cm, height=3.9cm, scale only axis,",
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
        rf"{{\footnotesize 图：{tex_escape(r['名称'])}月度收盘价（元）与 ZigZag 周期骨架"
        rf"（阈值 {ZZ_PCT * 100:.0f}\%，圆点为周期转折点）。}}",
        r"\end{center}",
    ])


FIN_ROWS = [("营业收入（亿元）", "营收亿"), ("归母净利润（亿元）", "归母亿"),
            ("毛利率（\\%）", "毛利率"), ("ROE（\\%）", "ROE"),
            ("资产负债率（\\%）", "负债率"), ("经营活动现金流净额（亿元）", "现金流亿")]


def fin_table(r: dict) -> str:
    cols = [("20231231", "2023 年"), ("20241231", "2024 年"),
            ("20251231", "2025 年"), (H1, "2026 年半年报")]
    L = [r"\begin{center}\small",
         r"\begin{tabular}{@{}lrrrr@{}}", r"\toprule",
         "指标 & " + " & ".join(c[1] for c in cols) + r" \\", r"\midrule"]
    for label, key in FIN_ROWS:
        vals = []
        for p, _ in cols:
            v = r[key].get(p, np.nan)
            vals.append(yi(v, 2) if key in ("营收亿", "归母亿", "现金流亿") else dash(v, 1))
        L.append(label + " & " + " & ".join(vals) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", "",
          r"{\footnotesize 表：关键财务指标（合并报表口径；2026 年半年报数据未年化）。}",
          r"\end{center}"]
    return "\n".join(L)


def esc_pct(s: str) -> str:
    """把未转义的 % 写成 \\%；LaTeX 中 % 是注释符，漏转会截断整段文字。"""
    return re.sub(r"(?<!\\)%", r"\\%", s)


def tex_company(r: dict) -> str:
    # 逐公司画像并入所属行业章的“上市公司画像”小节，故公司层级用 \subsubsection
    L = [r"\subsubsection{%s（%s）}" % (tex_escape(r["名称"]), r["代码"]),
         r"\label{co:%s}" % r["代码"], ""]
    L += [r"\pfl{公司基本情况} " + para_basic(r), ""]
    L += [r"\pfl{历史股价} " + para_price(r), ""]
    L += [chart(r), ""]
    L += [r"\pfl{过去周期分析} " + para_cycle(r), ""]
    L += [r"\pfl{盈利情况} " + para_profit(r), ""]
    L += [fin_table(r), ""]
    L += [r"\pfl{财务分析} " + para_finance(r), ""]
    L += [r"\pfl{重大战略转型} " + para_strategy(r), ""]
    L += [r"\pfl{历史融投资情况} " + para_invest(r), ""]
    L += [r"\pfl{未来潜在融资需求分析} " + para_need(r), ""]
    L.append("")
    return esc_pct("\n".join(L))


def write_dat(r: dict) -> None:
    px = r["px"]
    with open(os.path.join(PROF, f"px_{r['代码']}.dat"), "w", encoding="utf-8") as fh:
        fh.write("x y\n")
        for d, v in px.items():
            fh.write(f"{dec_year(d):.4f} {float(v):.4f}\n")
    kept = zigzag_kept(px)
    with open(os.path.join(PROF, f"pxzz_{r['代码']}.dat"), "w", encoding="utf-8") as fh:
        fh.write("x y\n")
        for d, v in kept:
            fh.write(f"{dec_year(pd.Timestamp(d)):.4f} {float(v):.4f}\n")


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
            out.append(tex_company(r))
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

    # ---- 2026 年半年报概览表（附录） ----
    h1 = df[["代码", "名称", "三级", "营收2026H1亿", "营收2026H1同比%",
             "归母2026H1亿", "负债率2026H1"]].copy()
    h1 = h1.sort_values("营收2026H1亿", ascending=False, na_position="last")
    out = [r"\begingroup\scriptsize\setlength{\tabcolsep}{2pt}",
           r"\begin{longtable}{@{}llp{2.4cm}rrrr@{}}",
           r"\caption{农业上市公司 2026 年半年报经营概览（按营业收入降序；合并报表口径，未年化，资产负债率为 2026 年 6 月末）}"
           r"\label{tab:company-h1}\\\\", r"\toprule",
           r"代码 & 公司简称 & 申万三级行业 & 营业收入（亿元） & 同比（\%） & 归母净利润（亿元） & 资产负债率（\%） \\",
           r"\midrule", r"\endfirsthead",
           r"\multicolumn{7}{l}{\small（续）}\\", r"\toprule",
           r"代码 & 公司简称 & 申万三级行业 & 营业收入（亿元） & 同比（\%） & 归母净利润（亿元） & 资产负债率（\%） \\",
           r"\midrule", r"\endhead", r"\bottomrule", r"\endlastfoot"]
    for _, r in h1.iterrows():
        out.append(" & ".join([
            r["代码"], tex_escape(r["名称"]), tex_escape(r["三级"]),
            yi(r["营收2026H1亿"]), zz(r["营收2026H1同比%"]) .replace("%", r"\%"),
            yi(r["归母2026H1亿"]), dash(r["负债率2026H1"], 1)]) + r" \\")
    out += [r"\end{longtable}",
            r"\endgroup"]
    with open(os.path.join(GENROOT, "company_h1_2026.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    # ---- 摘要 ----
    n26 = int(df["归母2026H1亿"].notna().sum()) if "归母2026H1亿" in df else 0
    log(f"\n## 覆盖情况\n")
    log(f"- 有月度行情（≥12 个月）：{len(recs)} 家")
    log(f"- 有 2026 年半年报归母净利润：{n26} 家")
    log(f"- 2025 年亏损：{int((pd.to_numeric(df['归母2025亿'], errors='coerce') < 0).sum())} 家")
    log(f"- 2026 年上半年亏损：{int((pd.to_numeric(df['归母2026H1亿'], errors='coerce') < 0).sum())} 家")
    log(f"- 资产负债率 > 65%（2025）："
        f"{int((pd.to_numeric(df['负债率2025'], errors='coerce') > 65).sum())} 家")
    with open(os.path.join(NOTES, "company_profiles_summary.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(str(x) for x in LOG) + "\n")
    log(f"\n→ {CLEAN}/company_profiles.csv, {CLEAN}/profiles/*.dat, {GEN}/*.tex")


if __name__ == "__main__":
    main()
