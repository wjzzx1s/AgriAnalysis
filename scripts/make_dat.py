#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 data/raw 的原始数据加工为：
  1) data/clean/*.dat —— pgfplots 直接读取的作图数据（两列：x=十进制年份, y=数值）
  2) data/clean/*.csv —— 分析结果表（周期划分、相关性、波动率、领先滞后等）
  3) notes/data_summary.md —— 供撰写正文引用的关键数字摘要

设计原则：所有结论性数字都从原始数据现算，正文只引用本脚本产出的数值。
"""
from __future__ import annotations

import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CLEAN, NOTES, RAW, load_raw  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 80)

LOG: list[str] = []


def log(s: str = "") -> None:
    print(s)
    LOG.append(s)


# ---------------------------------------------------------------- 基础工具
def dec_year(ts) -> float:
    """时间 → 十进制年份（2021-07 → 2021.5）"""
    t = pd.Timestamp(ts)
    return round(t.year + (t.month - 1) / 12 + (t.day - 1) / 365.25, 4)


def load_fut(sym: str) -> pd.DataFrame | None:
    df = load_raw(f"fut_{sym}")
    if df is None or df.empty:
        return None
    df = df.rename(columns={"日期": "date", "收盘价": "close", "成交量": "vol",
                            "持仓量": "oi"})
    df["date"] = pd.to_datetime(df["date"])
    for c in ("close", "vol", "oi"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date")
    return df[["date", "close", "vol", "oi"]].reset_index(drop=True)


def month_series(df: pd.DataFrame, how: str = "mean") -> pd.Series:
    s = df.set_index("date")["close"]
    return s.resample("ME").mean() if how == "mean" else s.resample("ME").last()


def rebase(s: pd.Series, base: str | None = None) -> pd.Series:
    """以 base 月份（如 '2021-01'）为 100 归一化；base 之前的数据丢弃。"""
    s = s.dropna()
    if base is not None:
        s = s[s.index >= pd.Timestamp(base) + pd.offsets.MonthBegin(0)]
    if len(s) == 0:
        return s
    return s / s.iloc[0] * 100.0


def write_dat(name: str, xs, ys, header: str = "xy") -> None:
    with open(os.path.join(CLEAN, f"{name}.dat"), "w", encoding="utf-8") as fh:
        fh.write(f"# {header}\n")
        for x, y in zip(xs, ys):
            if y is None or (isinstance(y, float) and np.isnan(y)):
                continue
            fh.write(f"{x} {y:.4f}\n")


def write_multi_dat(name: str, series: dict[str, pd.Series], base: str | None,
                    header: str = "多品种月度序列（十进制年份 + 各列）") -> list[str]:
    """多列 .dat：第一列 x，后续列按 series 顺序；缺失值用 NaN 跳过（pgfplots 用 nan）。"""
    cols = list(series.keys())
    idx = sorted(set().union(*[set(s.index) for s in series.values()]))
    with open(os.path.join(CLEAN, f"{name}.dat"), "w", encoding="utf-8") as fh:
        fh.write(f"# x {' '.join(cols)}\n")
        for t in idx:
            row = [f"{dec_year(t):.4f}"]
            for c in cols:
                v = series[c].get(t, np.nan)
                row.append("nan" if v is None or (isinstance(v, float) and np.isnan(v))
                           else f"{v:.4f}")
            fh.write(" ".join(row) + "\n")
    return cols


# ---------------------------------------------------------------- 品种定义
FUT_META = {
    "LH": ("生猪", "养殖"), "JD": ("鸡蛋", "养殖"),
    "C": ("玉米", "粮食"), "CS": ("玉米淀粉", "粮食"), "RR": ("粳米", "粮食"),
    "JR": ("粳稻", "粮食"), "RI": ("早籼稻", "粮食"), "WH": ("强麦", "粮食"),
    "A": ("豆一", "油料"), "B": ("豆二", "油料"), "RS": ("油菜籽", "油料"),
    "PK": ("花生", "油料"),
    "M": ("豆粕", "压榨链"), "RM": ("菜粕", "压榨链"),
    "Y": ("豆油", "压榨链"), "OI": ("菜油", "压榨链"), "P": ("棕榈油", "压榨链"),
    "SR": ("白糖", "软商品"), "CF": ("棉花", "软商品"), "CY": ("棉纱", "软商品"),
    "RU": ("天然橡胶", "软商品"), "NR": ("20号胶", "软商品"),
    "AP": ("苹果", "林果"), "CJ": ("红枣", "林果"),
    "SP": ("纸浆", "其他"),
}
# 主要分析品种（成交持仓活跃、贴合农业）
CORE = ["LH", "JD", "C", "M", "RM", "Y", "P", "SR", "CF", "AP", "CJ", "PK", "RU"]
GROUPS: dict[str, list[str]] = {
    "hog": ["LH", "JD"],
    "grain": ["C", "CS", "WH", "RR", "RI", "JR"],
    "oilseed": ["A", "B", "M", "RM", "Y", "OI", "P", "RS", "PK"],
    "soft": ["SR", "CF", "CY", "RU", "NR"],
    "fruit": ["AP", "CJ"],
}

SW_L2 = {"801011": "林业", "801012": "农产品加工", "801014": "饲料", "801015": "渔业",
         "801016": "种植业", "801017": "养殖业", "801018": "动物保健",
         "801019": "农业综合"}
SW_L3 = {"850111": "种子", "850112": "粮食种植", "850113": "其他种植业", "850114": "食用菌",
         "850121": "海洋捕捞", "850122": "水产养殖", "850131": "林业",
         "850142": "畜禽饲料", "850143": "水产饲料", "850144": "宠物食品",
         "850151": "果蔬加工", "850152": "粮油加工", "850154": "其他农产品加工",
         "850172": "生猪养殖", "850173": "肉鸡养殖", "850174": "其他养殖",
         "850181": "动物保健Ⅲ"}


# ---------------------------------------------------------------- 1. 期货月度序列
def build_futures_tables() -> dict[str, pd.Series]:
    log("\n## 2. 品种价格序列（期货主力连续）\n")
    monthly: dict[str, pd.Series] = {}
    rows = []
    for sym, (nm, cat) in FUT_META.items():
        df = load_fut(sym)
        if df is None or len(df) < 60:
            log(f"- `{nm}({sym})` 数据不足，跳过")
            continue
        m = month_series(df)
        monthly[sym] = m
        reb = rebase(m, "2021-01") if m.index[0] <= pd.Timestamp("2021-01-31") else rebase(m)
        write_dat(f"fut_m_{sym}", [dec_year(t) for t in m.index], m.values,
                  header=f"{nm}({sym}) 月度均价 元/吨")
        write_dat(f"fut_r_{sym}", [dec_year(t) for t in reb.index], reb.values,
                  header=f"{nm}({sym}) 月度价格指数 2021-01=100")
        ret = np.log(m / m.shift(1)).dropna()
        rows.append({
            "代码": sym, "品种": nm, "大类": cat,
            "起始": m.index[0].strftime("%Y-%m"), "结束": m.index[-1].strftime("%Y-%m"),
            "月度数": len(m), "均价": round(m.mean(), 1),
            "最新": round(m.iloc[-1], 1),
            "区间涨跌%": round((m.iloc[-1] / m.iloc[0] - 1) * 100, 1),
            "年化波动%": round(ret.std() * np.sqrt(12) * 100, 1),
            "历史最高": round(m.max(), 1), "历史最低": round(m.min(), 1),
            "峰谷比": round(m.max() / m.min(), 2),
        })
    t = pd.DataFrame(rows).sort_values("大类")
    t.to_csv(f"{CLEAN}/fut_summary.csv", index=False, encoding="utf-8-sig")
    log(t.to_string(index=False))
    return monthly


# ---------------------------------------------------------------- 2. 相关系数
def corr_matrix(monthly: dict[str, pd.Series], syms: list[str], start="2019-01"):
    rets = {}
    for s in syms:
        if s not in monthly:
            continue
        r = np.log(monthly[s] / monthly[s].shift(1)).dropna()
        r = r[r.index >= pd.Timestamp(start)]
        if len(r) >= 24:
            rets[s] = r
    if not rets:
        return None
    df = pd.DataFrame(rets).dropna(how="all")
    return df.corr(min_periods=24)


def write_heatmap_dat(name: str, corr: pd.DataFrame, labels: list[str]) -> None:
    with open(os.path.join(CLEAN, f"{name}.dat"), "w", encoding="utf-8") as fh:
        fh.write("# i j rho\n")
        for i, a in enumerate(corr.index):
            for j, b in enumerate(corr.columns):
                v = corr.loc[a, b]
                if pd.notna(v):
                    fh.write(f"{i} {j} {v:.4f}\n")
    with open(os.path.join(CLEAN, f"{name}_labels.dat"), "w", encoding="utf-8") as fh:
        for i, lb in enumerate(labels):
            fh.write(f"{i} {lb}\n")


def build_corr(monthly: dict[str, pd.Series]) -> None:
    log("\n## 3. 跨品种月度收益率相关性\n")
    syms = [s for s in FUT_META if s in monthly]
    corr = corr_matrix(monthly, syms)
    if corr is None:
        log("相关性数据不足")
        return
    labels = [FUT_META[s][0] for s in corr.columns]
    corr.to_csv(f"{CLEAN}/corr_futures.csv", encoding="utf-8-sig")
    write_heatmap_dat("corr_futures", corr, labels)
    log(f"- 样本期：{syms}；品种数 {len(corr)}")
    # 以生猪为中心的相关性排序
    if "LH" in corr.index:
        s = corr["LH"].drop("LH").sort_values(ascending=False)
        s.to_csv(f"{CLEAN}/corr_with_hog.csv", encoding="utf-8-sig", header=["相关系数"])
        log("- 与生猪期货相关性（|ρ| 降序）：")
        log("\n".join(f"  - {FUT_META[k][0]}: {v:+.2f}" for k, v in
                      s.reindex(s.abs().sort_values(ascending=False).index).items()))

    # 分组成对相关性均值（用于检验“养殖内部相关 > 跨类相关”）
    pairs = []
    for i, a in enumerate(corr.columns):
        for b in corr.columns[i + 1:]:
            pairs.append({"品种A": FUT_META[a][0], "品种B": FUT_META[b][0],
                          "大类A": FUT_META[a][1], "大类B": FUT_META[b][1],
                          "相关系数": corr.loc[a, b]})
    p = pd.DataFrame(pairs)
    p.to_csv(f"{CLEAN}/corr_pairs.csv", index=False, encoding="utf-8-sig")
    g = p.groupby(["大类A", "大类B"])["相关系数"].agg(["mean", "count"]).round(3)
    g.to_csv(f"{CLEAN}/corr_group_mean.csv", encoding="utf-8-sig")
    log("\n- 大类间平均相关系数：")
    log(g[(g["count"] >= 1)].to_string())


# ---------------------------------------------------------------- 3. 领先滞后
def build_leadlag(monthly: dict[str, pd.Series], max_lag: int = 12) -> None:
    log("\n## 4. 以猪价为基准的领先/滞后相关（月度）\n")
    if "LH" not in monthly:
        log("无生猪期货数据")
        return
    base = np.log(monthly["LH"] / monthly["LH"].shift(1)).dropna()
    rows = []
    for sym, (nm, cat) in FUT_META.items():
        if sym == "LH" or sym not in monthly:
            continue
        other = np.log(monthly[sym] / monthly[sym].shift(1)).dropna()
        best = None
        vals = []
        for lag in range(-max_lag, max_lag + 1):
            # lag>0：其他品种滞后于生猪（生猪领先）
            x = base.shift(lag)
            pair = pd.concat([x, other], axis=1).dropna()
            if len(pair) < 20:
                continue
            r = pair.iloc[:, 0].corr(pair.iloc[:, 1])
            vals.append((lag, r))
            if best is None or abs(r) > abs(best[1]):
                best = (lag, r)
        if vals:
            with open(os.path.join(CLEAN, f"leadlag_{sym}.dat"), "w",
                      encoding="utf-8") as fh:
                fh.write(f"# lag(月) corr  {nm} vs 生猪\n")
                for lag, r in vals:
                    fh.write(f"{lag} {r:.4f}\n")
            rows.append({"品种": nm, "代码": sym, "大类": cat,
                         "同期相关": round(dict(vals).get(0, np.nan), 3),
                         "最大相关": round(best[1], 3),
                         "对应滞后月": best[0],
                         "解读": ("猪价领先" if best[0] > 0 else
                                  ("同步" if best[0] == 0 else "其他品种领先"))})
    t = pd.DataFrame(rows).sort_values("最大相关", key=lambda s: s.abs(), ascending=False)
    t.to_csv(f"{CLEAN}/leadlag_summary.csv", index=False, encoding="utf-8-sig")
    log(t.to_string(index=False))


# ---------------------------------------------------------------- 4. 猪周期划分
def build_hog_cycle(monthly: dict[str, pd.Series]) -> None:
    log("\n## 5. 猪周期识别（生猪价格指数/期货）\n")
    hs = load_raw("hog_spot_index")
    if hs is not None and len(hs):
        hs["日期"] = pd.to_datetime(hs["日期"])
        hs = hs.sort_values("日期")
        c = "指数" if "指数" in hs.columns else hs.columns[1]
        hs[c] = pd.to_numeric(hs[c], errors="coerce")
        s = hs.set_index("日期")[c].resample("ME").mean()
        write_dat("hog_spot_m", [dec_year(t) for t in s.index], s.values,
                  header="生猪价格指数（月度，元/公斤）")
        for col in ("4个月均线", "6个月均线", "12个月均线", "成交均重"):
            if col in hs.columns:
                v = pd.to_numeric(hs[col], errors="coerce")
                if col in ("成交均重",):
                    v = v.where(v > 0)          # 早期数据为 0，视为缺失
                keep = v.notna()
                if int(keep.sum()) < 12:
                    continue
                mm = pd.Series(v[keep].values,
                               index=hs.loc[keep, "日期"]).resample("ME").mean()
                write_dat(f"hog_spot_{col.replace('个月','m').replace('均线','ma').replace('成交','')}",
                          [dec_year(t) for t in mm.index], mm.values,
                          header=f"生猪{col}")
                log(f"- 指标 `{col}`：最新 {v.dropna().iloc[-1]:.2f}，样本 {len(v.dropna())}")

    # 周期拐点：对月度序列做 3 个月的局部极值判定（窗口 ±w）
    def turning_points(s: pd.Series, w: int = 4, thr: float = 0.06):
        s = s.dropna()
        tp = []
        for i in range(w, len(s) - w):
            win = s.iloc[i - w:i + w + 1]
            v = s.iloc[i]
            if v == win.max() and v >= win.min() * (1 + thr):
                tp.append((s.index[i], "峰", v))
            elif v == win.min() and v <= win.max() * (1 - thr):
                tp.append((s.index[i], "谷", v))
        return tp

    if "LH" in monthly:
        tp = turning_points(monthly["LH"], w=3, thr=0.08)
        t = pd.DataFrame(tp, columns=["月份", "类型", "价格"])
        t["月份"] = t["月份"].dt.strftime("%Y-%m")
        t.to_csv(f"{CLEAN}/hog_cycle_turning_points.csv", index=False, encoding="utf-8-sig")
        log(f"- 生猪期货月度拐点（±3 月窗口、8% 幅度阈值）共 {len(t)} 个：")
        log(t.to_string(index=False))

    # 产能与成本指标（玄田数据）：能繁母猪存栏、猪粮比价、仔猪与二元母猪价格
    cap = load_raw("xt_supply_生猪产能")
    if cap is not None and len(cap):
        y = cap[cap["周期"].astype(str).str.match(r"^\d{4}$")].copy()
        y["年"] = y["周期"].astype(int)
        y = y.sort_values("年")
        for col in ["能繁母猪存栏", "生猪存栏", "生猪出栏", "猪肉产量"]:
            v = pd.to_numeric(y[col], errors="coerce")
            v = v[v > 0]
            if len(v) < 5:
                continue
            write_dat(f"hog_{col}_y", y.loc[v.index, "年"].values, v.values,
                      header=f"全国{col} 年度（万头 / 万吨）")
        log("\n- 全国生猪产能年度数据（万头、万吨）：")
        log(y[["年", "能繁母猪存栏", "生猪存栏", "生猪出栏", "猪肉产量"]].to_string(index=False))
        q = cap[~cap["周期"].astype(str).str.match(r"^\d{4}$")].copy()

        # 追加官方公开发布的最新期次（2025 年年度与 2026 年季度/月度）：
        # akshare 的“生猪产能”接口最新只到 2025 年 10 月，而报告的产业事实引用
        # 国家统计局 2025 年年度数据与农业农村部 2026 年发布会口径（见 notes/research/
        # A-hog-feed.md 的逐条引文与链接）。数据来源逐行记录在
        # data/raw/hog_capacity_official.csv 的“来源”列，便于核对。
        off = load_raw("hog_capacity_official")
        if off is not None and len(off):
            keep = ["周期", "能繁母猪存栏", "猪肉产量", "生猪存栏", "生猪出栏"]
            add = off[[c for c in keep if c in off.columns]].copy()
            q = pd.concat([q[[c for c in keep if c in q.columns]], add],
                          ignore_index=True)
            log(f"- 追加官方发布期次 {len(add)} 行（来源见 hog_capacity_official.csv）")

        q.to_csv(f"{CLEAN}/hog_capacity_recent.csv", index=False, encoding="utf-8-sig")
        log("\n- 最新季度/月度产能：")
        log(q.to_string(index=False))

        # 2025 年季度/月度能繁母猪存栏 → 十进制年份序列，供与年度序列拼接作图
        rows = []
        for _, r in q.iterrows():
            s = str(r["周期"])
            m = re.search(r"(\d{4})", s)
            if not m:
                continue
            yr = int(m.group(1))
            mm = None
            qm = re.search(r"([一二三四])季度", s)
            if qm:
                mm = {"一": 3, "二": 6, "三": 9, "四": 12}[qm.group(1)]
            else:
                mm2 = re.search(r"(\d{1,2})月", s)
                if mm2:
                    mm = int(mm2.group(1))
                elif re.search(r"全年|年末", s):
                    # 年度数据（如“2025年（全年/年末）”）落在当年 12 月
                    mm = 12
            try:
                val = float(r["能繁母猪存栏"])
            except (TypeError, ValueError):
                continue
            if mm is None or val <= 0:
                continue
            rows.append((yr, mm, val))
        rows.sort()
        if rows:
            write_dat("hog_能繁母猪存栏_q",
                      [round(y + (m - 1) / 12.0, 4) for y, m, _ in rows],
                      [v for _, _, v in rows],
                      header="能繁母猪存栏 季度/月度（万头）")
            log(f"- 2025 年产能序列已写出（{len(rows)} 个观测）")

    for key, nm, unit in [("xt_supply_猪粮比价", "猪粮比价", "倍"),
                          ("xt_cost_仔猪价格", "仔猪价格", "元/公斤"),
                          ("xt_cost_二元母猪价格", "二元母猪价格", "元/公斤"),
                          ("xt_cost_玉米", "玉米（玄田）", "元/吨"),
                          ("xt_cost_豆粕", "豆粕（玄田）", "元/吨"),
                          ("xt_supply_白条肉", "白条肉出厂价", "元/公斤"),
                          ("xt_supply_猪肉批发价", "猪肉批发价", "元/公斤"),
                          ("xt_supply_储备冻猪肉", "储备冻猪肉", "万吨"),
                          ("xt_supply_肉类价格指数", "肉类价格指数", "指数"),
                          ("xt_supply_育肥猪", "育肥猪价格", "元/公斤")]:
        df = load_raw(key)
        if df is None or df.empty:
            continue
        # 周度格式（2018年第01周）单独处理
        if "周期" in df.columns and df["周期"].astype(str).str.contains("周").any():
            wk = df["周期"].astype(str).str.extract(r"(\d{4})年第(\d{1,2})周")
            yrs = pd.to_numeric(wk[0], errors="coerce")
            wks = pd.to_numeric(wk[1], errors="coerce")
            val = pd.to_numeric(df.get("白条肉平均出厂价格"), errors="coerce")
            ok = yrs.notna() & wks.notna() & val.notna()
            xs = (yrs[ok] + (wks[ok] - 1) / 52.0).round(4)
            log(f"- `{nm}`（周度）：{int(ok.sum())} 个观测，"
                f"{int(yrs[ok].min())} 至 {int(yrs[ok].max())}")
            write_dat(f"hogx_{nm}", xs.values, val[ok].values, header=f"{nm} 周度（{unit}）")
            continue
        if "date" not in df.columns and "周期" in df.columns:
            log(f"- `{nm}`：{len(df)} 行，列 {list(df.columns)}（未作图）")
            continue
        if "date" in df.columns:
            vcol = next((c for c in ("value", "benzhou", "价格") if c in df.columns), None)
            if vcol is None:
                log(f"- `{nm}`：{len(df)} 行，列 {list(df.columns)}（无可识别数值列）")
                continue
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            v = pd.to_numeric(df[vcol], errors="coerce")
            if nm == "储备冻猪肉":
                v = v.where(v > 0)
            ok = df["date"].notna() & v.notna()
            mm = pd.Series(v[ok].values, index=df.loc[ok, "date"]).resample("ME").mean()
            write_dat(f"hogx_{nm.replace('（玄田）', '')}",
                      [dec_year(t) for t in mm.index], mm.values,
                      header=f"{nm} 月度（{unit}）")
            log(f"- `{nm}`：{int(ok.sum())} 个观测，"
                f"{df.loc[ok, 'date'].min():%Y-%m} 至 {df.loc[ok, 'date'].max():%Y-%m}，"
                f"最新 {v[ok].iloc[-1]:.2f}") if ok.sum() else log(f"- `{nm}` 无有效观测")


# ---------------------------------------------------------------- 5. 申万行业指数
def build_sw(monthly: dict[str, pd.Series]) -> None:
    log("\n## 6. 申万农业子行业指数（月度，2014-01=100 相对强弱）\n")
    idx: dict[str, pd.Series] = {}
    allcodes = {"801010": "农林牧渔"} | SW_L2 | SW_L3
    for code, nm in allcodes.items():
        df = load_raw(f"sw_hist_{code}_day")
        if df is None or df.empty:
            continue
        df["日期"] = pd.to_datetime(df["日期"])
        s = df.set_index("日期")["收盘"].astype(float).resample("ME").last().dropna()
        if len(s) < 24:
            log(f"- `{nm}({code})` 样本不足")
            continue
        idx[code] = s
        write_dat(f"sw_m_{code}", [dec_year(t) for t in s.index], s.values,
                  header=f"申万{nm}指数 月度收盘")
    if not idx:
        return
    # 归一化：以 2021-01 为 100
    reb = {f"sw{code}": rebase(s, "2021-01") for code, s in idx.items()
           if s.index[0] <= pd.Timestamp("2021-01-31")}
    if reb:
        write_multi_dat("sw_rebased2021", reb, None,
                        header="申万农业行业指数 2021-01=100")
        log(f"- 归一化系列：{list(reb)}")

    rows = []
    for code, s in idx.items():
        nm = allcodes.get(code, code)
        y23 = s[s.index >= "2023-01-01"]
        rows.append({
            "行业代码": code, "行业名称": nm,
            "起始": s.index[0].strftime("%Y-%m"), "最新": round(s.iloc[-1], 1),
            "近1年涨跌%": round((s.iloc[-1] / s[s.index <= s.index[-1] - pd.DateOffset(years=1)].iloc[-1] - 1) * 100, 1)
            if len(s[s.index <= s.index[-1] - pd.DateOffset(years=1)]) else None,
            "近3年涨跌%": round((s.iloc[-1] / y23.iloc[0] - 1) * 100, 1) if len(y23) else None,
            "历史最高": round(s.max(), 1), "历史最低": round(s.min(), 1),
            "峰谷比": round(s.max() / s.min(), 2),
        })
    t = pd.DataFrame(rows)
    t.to_csv(f"{CLEAN}/sw_summary.csv", index=False, encoding="utf-8-sig")
    log(t.to_string(index=False))

    # 子行业与猪价的月度收益率相关性
    if "LH" in monthly:
        base = np.log(monthly["LH"] / monthly["LH"].shift(1)).dropna()
        rows = []
        for code, s in idx.items():
            r = np.log(s / s.shift(1)).dropna()
            pair = pd.concat([base, r], axis=1).dropna()
            if len(pair) < 24:
                continue
            rows.append({"行业代码": code, "行业名称": allcodes.get(code, code),
                         "层级": "二级" if code in SW_L2 else ("三级" if code in SW_L3 else "一级"),
                         "与生猪期货月收益相关": round(pair.iloc[:, 0].corr(pair.iloc[:, 1]), 3),
                         "样本月数": len(pair)})
        t2 = pd.DataFrame(rows).sort_values("与生猪期货月收益相关", ascending=False)
        t2.to_csv(f"{CLEAN}/sw_corr_hog.csv", index=False, encoding="utf-8-sig")
        log("\n- 子行业指数与生猪期货月度收益率相关性：")
        log(t2.to_string(index=False))
        with open(os.path.join(CLEAN, "sw_corr_hog.dat"), "w", encoding="utf-8") as fh:
            fh.write("# i rho\n")
            for i, (_, r) in enumerate(t2.iterrows()):
                fh.write(f"{i} {r['与生猪期货月收益相关']:.4f}\n")
        with open(os.path.join(CLEAN, "sw_corr_hog_labels.dat"), "w", encoding="utf-8") as fh:
            for i, (_, r) in enumerate(t2.iterrows()):
                fh.write(f"{i} {r['行业名称']}\n")


# ---------------------------------------------------------------- 6. 宏观需求
def build_macro() -> None:
    log("\n## 7. 需求侧宏观指标\n")
    cpi = load_raw("macro_cpi_yearly")
    if cpi is not None:
        cpi["日期"] = pd.to_datetime(cpi["日期"])
        food = cpi[cpi["商品"].astype(str).str.contains("食品|粮食|肉|鲜菜|蛋|水产品")]
        if len(food):
            piv = food.pivot_table(index="日期", columns="商品", values="今值")
            piv.to_csv(f"{CLEAN}/cpi_food.csv", encoding="utf-8-sig")
            log(f"- CPI 分项可用：{list(piv.columns)}")
            latest = piv.dropna(how="all").iloc[-1]
            log("- 最新一期 CPI 分项同比：")
            log("\n".join(f"  - {k}: {v}" for k, v in latest.dropna().items()))
    for key, nm in [("macro_retail", "社会消费品零售总额"),
                    ("macro_qyspjg", "企业商品价格指数"),
                    ("macro_agri_index", "农产品价格指数"),
                    ("macro_agri_product", "农产品价格")]:
        df = load_raw(key)
        if df is None or df.empty:
            continue
        log(f"- `{nm}`：{len(df)} 行，列 {list(df.columns)[:8]}")


# ---------------------------------------------------------------- 主流程
def main() -> None:
    log("# 数据分析摘要（自动生成，make_dat.py）\n")
    log(f"生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M}")

    log("\n## 1. 原始数据清单\n")
    man = load_raw("_manifest")
    files = sorted(f for f in os.listdir(RAW) if f.endswith(".csv"))
    log(f"- data/raw 下 CSV 文件 {len(files)} 个")

    monthly = build_futures_tables()
    # 跨品种相关性、领先滞后与阶段分析见 scripts/analyze_corr.py
    build_hog_cycle(monthly)
    build_sw(monthly)
    build_macro()

    with open(os.path.join(NOTES, "data_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + "\n")
    print(f"\n>> 摘要已写入 notes/data_summary.md（{len(LOG)} 行）")
    print(f">> .dat 文件：{len([f for f in os.listdir(CLEAN) if f.endswith('.dat')])} 个")


if __name__ == "__main__":
    main()
