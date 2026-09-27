#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""二次探测：EM 端点重试 + 申万农业行业树 + 成分股清单。"""
import time
import akshare as ak
import pandas as pd

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 80)
pd.set_option("display.max_rows", 200)


def tryit(label, fn, *a, retries=2, **kw):
    for i in range(retries + 1):
        try:
            df = fn(*a, **kw)
            print(f"[OK] {label} rows={len(df)} cols={list(df.columns)[:14]}")
            return df
        except Exception as e:
            if i == retries:
                print(f"[FAIL] {label} -> {type(e).__name__}: {str(e)[:120]}")
                return None
            time.sleep(2)


print("=== EM 端点重试 ===")
tryit("stock_board_industry_cons_em(农林牧渔)", ak.stock_board_industry_cons_em, symbol="农林牧渔")
tryit("stock_individual_info_em(000998)", ak.stock_individual_info_em, symbol="000998")
tryit("stock_info_a_code_name()", ak.stock_info_a_code_name)
tryit("stock_zh_a_hist(000998)", ak.stock_zh_a_hist, symbol="000998", period="daily",
      start_date="20230101", end_date="20260926", adjust="qfq")
tryit("stock_zh_a_daily(sz000998)", ak.stock_zh_a_daily, symbol="sz000998")

print("\n=== 申万行业树（农林牧渔） ===")
l1 = ak.sw_index_first_info()
print(l1.to_string())
l2 = ak.sw_index_second_info()
print(l2[l2["上级行业"].astype(str).str.contains("农林牧渔")].to_string())
l3 = ak.sw_index_third_info()
agri = l3[l3["上级行业"].astype(str).str.contains("农林牧渔|种植业|养殖业|饲料|动物保健|农产品加工|渔业|林业")]
print(agri.to_string())

print("\n=== 申万一级 801010 成分股 ===")
comp = ak.index_component_sw(symbol="801010")
print(len(comp))
print(comp.head(120).to_string())
comp.to_csv("data/raw/sw801010_components.csv", index=False, encoding="utf-8-sig")
