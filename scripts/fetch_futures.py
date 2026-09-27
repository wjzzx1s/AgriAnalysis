#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取农产品期货行情与库存/仓单数据。

产出：
  data/raw/fut_<SYM>.csv            主力连续日行情（新浪）
  data/raw/fut_inv_em_<name>.csv    东财期货库存
  data/raw/fut_inv99.csv            99期货库存（品种较全）
  data/raw/fut_warehouse_<exch>.csv 交易所仓单日报
  data/raw/fut_spot_basis.csv       现货价/基差快照
"""
from __future__ import annotations

import os
import sys
import time

import akshare as ak
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import exists, fetch, guard, save  # noqa: E402

# 品种 -> (主力连续代码, 交易所, 大类, 起始上市年份备注)
FUT = {
    "LH": ("生猪", "DCE", "养殖", 2021),
    "JD": ("鸡蛋", "DCE", "养殖", 2013),
    "C": ("玉米", "DCE", "粮食", 2004),
    "CS": ("玉米淀粉", "DCE", "粮食", 2014),
    "A": ("豆一", "DCE", "油料", 2002),
    "B": ("豆二", "DCE", "油料", 2004),
    "M": ("豆粕", "DCE", "饲料原料", 2000),
    "RM": ("菜粕", "CZCE", "饲料原料", 2012),
    "OI": ("菜油", "CZCE", "油脂", 2007),
    "Y": ("豆油", "DCE", "油脂", 2006),
    "P": ("棕榈油", "DCE", "油脂", 2007),
    "SR": ("白糖", "CZCE", "软商品", 2006),
    "CF": ("棉花", "CZCE", "软商品", 2004),
    "CY": ("棉纱", "CZCE", "软商品", 2017),
    "AP": ("苹果", "CZCE", "林果", 2017),
    "CJ": ("红枣", "CZCE", "林果", 2019),
    "PK": ("花生", "CZCE", "油料", 2021),
    "RU": ("天然橡胶", "SHFE", "软商品", 1993),
    "NR": ("20号胶", "INE", "软商品", 2019),
    "SP": ("纸浆", "SHFE", "其他", 2018),
    "RR": ("粳米", "DCE", "粮食", 2019),
    "RS": ("油菜籽", "CZCE", "油料", 2012),
    "JR": ("粳稻", "CZCE", "粮食", 2013),
    "RI": ("早籼稻", "CZCE", "粮食", 2009),
    "WH": ("强麦", "CZCE", "粮食", 2003),
    "PM": ("普麦", "CZCE", "粮食", 2003),
}

INV_EM_NAMES = ["生猪", "玉米", "豆粕", "白糖", "苹果", "鸡蛋", "豆油", "棕榈油",
                "菜油", "菜粕", "棉花", "棉纱", "红枣", "花生", "天然橡胶", "纸浆",
                "玉米淀粉", "豆一", "粳米", "油菜籽", "强麦"]


@guard("fetch_futures")
def main(force: bool = False):
    ok = fail = 0

    # 1) 主力连续日行情
    for sym, (name, exch, cat, yr) in FUT.items():
        fname = f"fut_{sym}"
        if exists(fname) and not force:
            ok += 1
            continue
        df = fetch(ak.futures_main_sina, symbol=f"{sym}0")
        if df is not None and len(df) > 0:
            df.insert(0, "品种", name)
            df.insert(1, "代码", sym)
            df.insert(2, "交易所", exch)
            df.insert(3, "大类", cat)
        if save(df, fname, f"新浪财经期货主力连续 futures_main_sina({sym}0)",
                note=f"{name} {exch}"):
            ok += 1
        else:
            fail += 1
        time.sleep(0.2)

    # 2) 东财期货库存（仅部分品种）
    for name in INV_EM_NAMES:
        fname = f"fut_inv_em_{name}"
        if exists(fname) and not force:
            continue
        df = fetch(ak.futures_inventory_em, symbol=name, retries=1, sleep=1.0)
        if df is not None:
            save(df, fname, f"东方财富期货库存 futures_inventory_em({name})", note=name)
            ok += 1
        time.sleep(0.2)

    # 3) 99 期货库存（品种全、历史长）
    if force or not exists("fut_inv99"):
        df = fetch(ak.futures_inventory_99, symbol="豆粕", retries=1)
        if df is not None:
            save(df, "fut_inv99_豆粕", "99期货 futures_inventory_99(豆粕)")
    for nm in ["玉米", "白糖", "棉花", "苹果", "鸡蛋", "菜粕", "豆油", "棕榈油"]:
        fname = f"fut_inv99_{nm}"
        if exists(fname) and not force:
            continue
        df = fetch(ak.futures_inventory_99, symbol=nm, retries=1, sleep=1.0)
        if df is not None:
            save(df, fname, f"99期货 futures_inventory_99({nm})", note=nm)
        time.sleep(0.2)

    # 4) 交易所仓单日报（按日期，取若干代表性日期由别处循环；此处只取最新）
    for fn_name in ["futures_to_spot_czce", "futures_to_spot_dce", "futures_to_spot_shfe"]:
        fname = f"fut_wh_{fn_name}"
        if exists(fname) and not force:
            continue
        fn = getattr(ak, fn_name, None)
        if fn is None:
            continue
        df = fetch(fn, date="20260925", retries=1, sleep=1.0)
        if df is not None:
            save(df, fname, f"akshare {fn_name}")

    # 5) 现货价与基差快照
    if force or not exists("fut_spot_basis"):
        df = fetch(ak.futures_spot_price_daily)
        if df is not None:
            save(df, "fut_spot_basis", "akshare futures_spot_price_daily")

    print(f"[fetch_futures] ok={ok} fail={fail}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
