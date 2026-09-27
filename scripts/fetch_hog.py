#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取生猪产业链现货与产业指标（猪易数据 + 玄田数据 + 99 期货期现）。

玄田数据（akshare futures_hog_*）提供三类指标，symbol 取值如下：
  核心价格 futures_hog_core:   外三元 / 内三元 / 土杂猪
  成本维度 futures_hog_cost:   玉米 / 豆粕 / 二元母猪价格 / 仔猪价格
  供应维度 futures_hog_supply: 猪肉批发价 / 储备冻猪肉 / 饲料原料数据 / 白条肉 /
                              生猪产能（能繁母猪存栏、猪肉产量、生猪存栏、生猪出栏）/
                              育肥猪 / 肉类价格指数 / 猪粮比价
"""
from __future__ import annotations

import os
import sys
import time

import akshare as ak

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import exists, fetch, guard, save  # noqa: E402

CORE_SYMS = ["外三元", "内三元", "土杂猪"]
COST_SYMS = ["玉米", "豆粕", "二元母猪价格", "仔猪价格"]
SUPPLY_SYMS = ["猪肉批发价", "储备冻猪肉", "饲料原料数据", "白条肉", "生猪产能",
               "育肥猪", "肉类价格指数", "猪粮比价"]

QH_SPOT = ["生猪", "鸡蛋", "玉米", "豆粕", "菜籽粕", "豆油", "棕榈油", "菜籽油",
           "白糖", "棉花", "苹果", "红枣", "花生", "玉米淀粉", "豆一"]

PLAIN = [
    ("hog_spot_index", ak.index_hog_spot_price, (), "猪易数据 index_hog_spot_price 生猪价格指数（含成交均重）"),
    ("hog_spot_province", ak.spot_hog_soozhu, (), "猪易数据 各省生猪价格"),
    ("hog_spot_lean", ak.spot_hog_lean_price_soozhu, (), "猪易数据 瘦肉型生猪价格"),
    ("hog_spot_crossbred", ak.spot_hog_crossbred_soozhu, (), "猪易数据 土杂猪价格"),
    ("hog_spot_threeway", ak.spot_hog_three_way_soozhu, (), "猪易数据 三元猪价格"),
    ("hog_year_trend", ak.spot_hog_year_trend_soozhu, (), "猪易数据 生猪价格年度走势"),
    ("feed_spot_mixed", ak.spot_mixed_feed_soozhu, (), "猪易数据 育肥猪配合饲料价格"),
    ("feed_spot_corn", ak.spot_corn_price_soozhu, (), "猪易数据 玉米现货价格"),
    ("feed_spot_soybean", ak.spot_soybean_price_soozhu, (), "猪易数据 豆粕现货价格"),
]


@guard("fetch_hog")
def main(force: bool = False):
    ok = fail = 0
    jobs = []
    for s in CORE_SYMS:
        jobs.append((f"xt_core_{s}", ak.futures_hog_core, (s,), f"玄田数据 生猪价格（{s}，元/公斤）"))
    for s in COST_SYMS:
        jobs.append((f"xt_cost_{s}", ak.futures_hog_cost, (s,), f"玄田数据 成本维度（{s}）"))
    for s in SUPPLY_SYMS:
        jobs.append((f"xt_supply_{s}", ak.futures_hog_supply, (s,), f"玄田数据 供应维度（{s}）"))
    for s in PLAIN:
        jobs.append(s)
    for s in QH_SPOT:
        jobs.append((f"qh_spot_{s}", ak.spot_price_qh, (s,), f"99期货 现货走势（{s}）"))

    for item in jobs:
        name, fn, args, src = item
        if exists(name) and not force:
            ok += 1
            continue
        df = fetch(fn, *args, retries=3, sleep=2.0)
        if save(df, name, src):
            ok += 1
        else:
            fail += 1
        time.sleep(0.25)
    print(f"[fetch_hog] ok={ok} fail={fail}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
