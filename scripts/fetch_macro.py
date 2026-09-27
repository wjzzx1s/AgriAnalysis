#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取需求侧与价格侧的宏观数据。

产出：
  data/raw/macro_cpi_yearly.csv               CPI 及其分项（含食品）
  data/raw/macro_food_cpi.csv                 食品类 CPI 细分（如可取）
  data/raw/macro_retail.csv                   社会消费品零售总额
  data/raw/macro_agri_index.csv               农产品价格指数（中价/农业板块）
  data/raw/macro_agri_product.csv             农产品价格（分品种）
  data/raw/macro_vegetable_basket.csv         “菜篮子”批发价格指数
  data/raw/macro_qyspjg.csv                   企业商品价格指数（农产品分项）
  data/raw/macro_pmi.csv                      PMI（制造业/非制造业）
  data/raw/macro_gdp.csv                      GDP
  data/raw/macro_ppi.csv                      PPI
"""
from __future__ import annotations

import os
import sys
import time

import akshare as ak

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import exists, fetch, guard, save  # noqa: E402

JOBS = [
    ("macro_cpi_yearly", ak.macro_china_cpi_yearly, (), "akshare macro_china_cpi_yearly"),
    ("macro_retail", ak.macro_china_consumer_goods_retail, (), "国家统计局 社会消费品零售总额"),
    ("macro_agri_index", ak.macro_china_agricultural_index, (), "中价指数 农产品价格指数"),
    ("macro_agri_product", ak.macro_china_agricultural_product, (), "中价指数 农产品价格"),
    ("macro_vegetable_basket", ak.macro_china_vegetable_basket, (), "中价指数 菜篮子价格"),
    ("macro_qyspjg", ak.macro_china_qyspjg, (), "中国人民银行 企业商品价格指数"),
    ("macro_pmi", ak.macro_china_pmi, (), "国家统计局 PMI"),
    ("macro_gdp", ak.macro_china_gdp, (), "国家统计局 GDP"),
    ("macro_ppi", ak.macro_china_ppi, (), "国家统计局 PPI"),
]


@guard("fetch_macro")
def main(force: bool = False):
    ok = fail = 0
    for name, fn, a, src in JOBS:
        if exists(name) and not force:
            ok += 1
            continue
        df = fetch(fn, *a, retries=3)
        if save(df, name, src):
            ok += 1
        else:
            fail += 1
        time.sleep(0.3)
    print(f"[fetch_macro] ok={ok} fail={fail}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
