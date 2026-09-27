#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取申万农林牧渔（801010）全部 A 股上市公司的公司画像数据。

每家公司抓取 8 类数据，落盘到 data/raw/company/<code>_<kind>.csv：
  profile      公司概况（巨潮）
  basic        个股基本信息（东财，含总市值/流通市值/行业）
  fin_abstract 财务摘要（关键指标 × 报告期）
  fin_ind      财务分析指标（杜邦/偿债/营运指标）
  zygc         主营构成（分产品/分地区）
  fhps         分红送转
  share_chg    股本变动（含增发/配股/送转史）
  gdhs         股东户数
  disc         巨潮信息披露公告（近三年，含标题+日期+链接）
  px           前复权日行情（新浪）
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CLEAN, RAW, exists, fetch, guard, load_raw, save  # noqa: E402

DISC_START, DISC_END = "20230901", "20260927"
WORKERS = 3


def market_prefix(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90")):
        return "sh"
    if code.startswith(("00", "30", "20")):
        return "sz"
    if code.startswith(("43", "83", "87", "92")):
        return "bj"
    return "sh"


def get_universe() -> pd.DataFrame:
    """取得申万农林牧渔全部成分股（优先用已生成的行业映射表）。"""
    p = os.path.join(CLEAN, "sw_stock_industry.csv")
    if os.path.exists(p):
        m = pd.read_csv(p, dtype={"股票代码": str}, encoding="utf-8-sig")
        l1 = m[m["行业层级"] == "一级"][["股票代码", "证券名称"]].drop_duplicates()
        if len(l1) >= 90:
            return l1
    c = load_raw("sw801010_components")
    if c is not None and len(c):
        return c.rename(columns={"证券代码": "股票代码", "证券名称": "证券名称"})[
            ["股票代码", "证券名称"]].astype({"股票代码": str})
    raise RuntimeError("无法获取成分股清单，请先运行 fetch_sw.py")


def mk_fhps(code: str) -> pd.DataFrame | None:
    """分红送转：优先巨潮（东财接口不稳定时的替代）。"""
    try:
        return ak.stock_dividend_cninfo(symbol=code)
    except Exception:  # noqa: BLE001
        return ak.stock_fhps_detail_em(symbol=code)


def mk_basic(code: str, pref: str) -> pd.DataFrame | None:
    """东财个股信息接口不可用时的替代：用新浪前复权日行情的最新收盘价
    与流通股本计算流通市值，附巨潮公司概况中的上市信息。"""
    px = ak.stock_zh_a_daily(symbol=f"{pref}{code}")
    if px is None or not len(px):
        return None
    px = px.dropna(subset=["close"])
    last = px.iloc[-1]
    out = {
        "股票代码": code,
        "最新收盘价": float(last["close"]),
        "流通股本(股)": float(last.get("outstanding_share", float("nan"))),
        "流通市值(元)": float(last["close"] * last.get("outstanding_share", float("nan"))),
        "数据日期": str(last["date"]),
        "近一年涨跌幅%": round(
            (float(last["close"]) / float(px[px["date"] <= px["date"].iloc[-1] -
             pd.Timedelta(days=365)]["close"].iloc[-1]) - 1) * 100, 2)
        if len(px[px["date"] <= px["date"].iloc[-1] - pd.Timedelta(days=365)]) else None,
    }
    return pd.DataFrame([out])


def fetch_one(code: str, name: str, force: bool = False) -> tuple[int, int]:
    code = str(code).zfill(6)
    pref = market_prefix(code)
    ok = fail = 0
    sub = "company"

    jobs = [
        ("profile", lambda: ak.stock_profile_cninfo(symbol=code),
         f"巨潮资讯网 stock_profile_cninfo({code})"),
        ("basic", lambda: mk_basic(code, pref),
         f"新浪财经日行情×流通股本 计算（EM 不可用时的替代口径）"),
        ("zyjs", lambda: ak.stock_zyjs_ths(symbol=code),
         f"同花顺 stock_zyjs_ths({code})"),
        ("fin_abstract", lambda: ak.stock_financial_abstract(symbol=code),
         f"新浪财经 stock_financial_abstract({code})"),
        ("fin_ind", lambda: ak.stock_financial_analysis_indicator(symbol=code, start_year="2022"),
         f"新浪财经 stock_financial_analysis_indicator({code})"),
        ("fhps", lambda: mk_fhps(code),
         f"巨潮资讯网 stock_dividend_cninfo({code})"),
        ("share_chg", lambda: ak.stock_share_change_cninfo(symbol=code),
         f"巨潮资讯网 stock_share_change_cninfo({code})"),
        ("disc", lambda: ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code, market="沪深京", start_date=DISC_START, end_date=DISC_END),
         f"巨潮资讯网 stock_zh_a_disclosure_report_cninfo({code})"),
        ("px", lambda: ak.stock_zh_a_daily(symbol=f"{pref}{code}"),
         f"新浪财经 stock_zh_a_daily({pref}{code})"),
    ]

    for kind, fn, src in jobs:
        fname = f"{code}_{kind}"
        if exists(fname, sub) and not force:
            ok += 1
            continue
        try:
            df = fn()
        except Exception as exc:  # noqa: BLE001
            df = fetch(fn, retries=2, sleep=1.5)
            if df is None:
                print(f"    [FAIL] {code} {name} {kind}: {type(exc).__name__} {str(exc)[:90]}")
                fail += 1
                continue
        if kind == "disc" and df is not None and len(df):
            keep = [c for c in ["代码", "简称", "公告标题", "公告时间", "公告链接"] if c in df.columns]
            df = df[keep]
        if kind == "px" and df is not None and "date" in df.columns:
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df[df["date"] >= pd.Timestamp("2021-01-01")]
        if save(df, fname, src, note=name, subdir=sub):
            ok += 1
        else:
            fail += 1
        time.sleep(0.15)
    return ok, fail


@guard("fetch_companies")
def main(force: bool = False):
    uni = get_universe()
    print(f"公司总数：{len(uni)}")
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, r["股票代码"], r.get("证券名称", ""), force): r["股票代码"]
                for _, r in uni.iterrows()}
        done = 0
        for f in as_completed(futs):
            try:
                o, fl = f.result()
            except Exception as exc:  # noqa: BLE001
                print(f"    [EXC] {futs[f]}: {type(exc).__name__} {exc}")
                o, fl = 0, 1
            ok += o
            fail += fl
            done += 1
            if done % 10 == 0:
                print(f"    进度 {done}/{len(uni)}  ok={ok} fail={fail}")
    print(f"[fetch_companies] ok={ok} fail={fail}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
