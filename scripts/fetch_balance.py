#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取上市公司的资产负债表与现金流量表关键科目（新浪财经接口）。

用途：为第二部分“历史融投资情况”与“未来潜在融资需求”提供可直接量化的证据——
货币资金、短期借款、一年内到期的非流动负债、长期借款、应付债券（有息负债构成），
以及取得借款/发行债券/吸收投资/偿还债务等筹资活动科目。

产出（data/raw/company/，逐家一个文件，仅保留白名单科目）：
  <code>_bs.csv   资产负债表（报告日 + 现金/存货/固定资产/在建工程/有息负债/净资产等）
  <code>_cf.csv   现金流量表（报告日 + 经营/投资/筹资活动净额、借款与偿债现金流）
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CLEAN, RAW, exists, fetch, guard, save  # noqa: E402

WORKERS = 3

BS_KEEP = ["报告日", "货币资金", "交易性金融资产", "应收票据及应收账款", "存货",
           "流动资产合计", "固定资产净额", "在建工程合计", "生产性生物资产", "无形资产",
           "商誉", "资产总计", "短期借款", "应付票据及应付账款", "合同负债",
           "一年内到期的非流动负债", "其他流动负债", "流动负债合计", "长期借款", "应付债券",
           "租赁负债", "非流动负债合计", "负债合计", "归属于母公司股东权益合计",
           "所有者权益(或股东权益)合计"]

CF_KEEP = ["报告日", "经营活动产生的现金流量净额", "投资活动产生的现金流量净额",
           "购建固定资产、无形资产和其他长期资产所支付的现金", "吸收投资收到的现金",
           "取得借款收到的现金", "发行债券收到的现金", "收到其他与筹资活动有关的现金",
           "筹资活动现金流入小计", "偿还债务支付的现金",
           "分配股利、利润或偿付利息所支付的现金", "支付其他与筹资活动有关的现金",
           "筹资活动现金流出小计", "筹资活动产生的现金流量净额"]


def market_prefix(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90")):
        return "sh"
    if code.startswith(("00", "30", "20")):
        return "sz"
    return "bj"


def trim(df: pd.DataFrame, keep: list[str]) -> pd.DataFrame:
    if df is None or not len(df):
        return df
    cols = [c for c in keep if c in df.columns]
    out = df[cols].copy()
    out["报告日"] = out["报告日"].astype(str)
    return out


def fetch_one(code: str, name: str, force: bool = False) -> tuple[int, int]:
    code = str(code).zfill(6)
    pref = market_prefix(code)
    ok = fail = 0
    for kind, kname, keep in (("bs", "资产负债表", BS_KEEP), ("cf", "现金流量表", CF_KEEP)):
        fname = f"{code}_{kind}"
        if exists(fname, "company") and not force:
            ok += 1
            continue
        df = fetch(ak.stock_financial_report_sina, stock=f"{pref}{code}", symbol=kname,
                   retries=3, sleep=1.5)
        if df is None or not len(df):
            print(f"    [FAIL] {code} {name} {kind}")
            fail += 1
            continue
        if save(trim(df, keep), fname,
                source=f"新浪财经 stock_financial_report_sina({pref}{code}, {kname})",
                note=name, subdir="company"):
            ok += 1
        else:
            fail += 1
        time.sleep(0.15)
    return ok, fail


@guard("fetch_balance")
def main(force: bool = False):
    uni = pd.read_csv(os.path.join(CLEAN, "sw_stock_industry.csv"),
                      dtype={"股票代码": str}, encoding="utf-8-sig")
    l1 = uni[uni["行业层级"] == "一级"][["股票代码", "证券名称"]].drop_duplicates("股票代码")
    print(f"公司总数：{len(l1)}")
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, r["股票代码"], r.get("证券名称", ""), force): r["股票代码"]
                for _, r in l1.iterrows()}
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
                print(f"    进度 {done}/{len(l1)}  ok={ok} fail={fail}")
    print(f"[fetch_balance] ok={ok} fail={fail}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
