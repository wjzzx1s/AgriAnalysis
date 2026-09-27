#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Probe akshare endpoints used by the AgriAnalysis project.

Writes a Markdown report of which endpoints work, their columns and row counts.
Usage: .venv/bin/python scripts/probe_akshare.py
"""
from __future__ import annotations

import io
import sys
import traceback
import contextlib

import akshare as ak
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)

OUT = io.StringIO()


def probe(name: str, fn, *args, **kwargs) -> None:
    try:
        df = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"### {name}\n\n- STATUS: **FAIL** `{type(exc).__name__}: {exc}`\n")
        return
    if df is None:
        print(f"### {name}\n\n- STATUS: **EMPTY(None)**\n")
        return
    if not isinstance(df, pd.DataFrame):
        print(f"### {name}\n\n- STATUS: **OK (non-frame {type(df).__name__})**: {str(df)[:400]}\n")
        return
    print(
        f"### {name}\n\n- STATUS: OK  rows={len(df)}  cols={list(df.columns)}\n"
    )
    with pd.option_context("display.max_columns", 60):
        print("```")
        print(df.head(3).to_string())
        print("```")
    print()


def main() -> None:
    print(f"akshare {ak.__version__} / pandas {pd.__version__}\n")

    print("## 期货主力连续（新浪）\n")
    for sym, label in [
        ("LH0", "生猪"),
        ("JD0", "鸡蛋"),
        ("C0", "玉米"),
        ("CS0", "玉米淀粉"),
        ("A0", "豆一"),
        ("B0", "豆二"),
        ("M0", "豆粕"),
        ("RM0", "菜粕"),
        ("OI0", "菜油"),
        ("Y0", "豆油"),
        ("P0", "棕榈油"),
        ("SR0", "白糖"),
        ("CF0", "棉花"),
        ("CY0", "棉纱"),
        ("AP0", "苹果"),
        ("CJ0", "红枣"),
        ("PK0", "花生"),
        ("RU0", "橡胶"),
        ("NR0", "20号胶"),
        ("SP0", "纸浆"),
        ("RR0", "粳米"),
        ("RS0", "菜籽"),
        ("JR0", "粳稻"),
        ("RI0", "早籼稻"),
        ("WH0", "强麦"),
        ("PM0", "普麦"),
    ]:
        probe(f"futures_main_sina({sym})  # {label}", ak.futures_main_sina, symbol=sym)

    print("## 生猪 / 饲料 现货与产业指标\n")
    probe("index_hog_spot_price()", ak.index_hog_spot_price)
    for fn in [
        "spot_hog_soozhu",
        "spot_hog_lean_price_soozhu",
        "spot_hog_crossbred_soozhu",
        "spot_hog_three_way_soozhu",
        "spot_hog_year_trend_soozhu",
        "spot_mixed_feed_soozhu",
        "spot_corn_price_soozhu",
        "spot_soybean_price_soozhu",
        "futures_hog_core",
        "futures_hog_cost",
        "futures_hog_supply",
    ]:
        fn_obj = getattr(ak, fn, None)
        if fn_obj is None:
            print(f"### {fn}()\n\n- STATUS: **MISSING**\n")
            continue
        probe(f"{fn}()", fn_obj)

    print("## 期货库存 / 现货基差\n")
    for sym in ["生猪", "玉米", "豆粕", "棉花", "白糖", "苹果"]:
        probe(f"futures_inventory_em('{sym}')", ak.futures_inventory_em, symbol=sym)
    probe("futures_spot_price_daily()", ak.futures_spot_price_daily)

    print("## 宏观 / 农业指数\n")
    probe("macro_china_agricultural_index()", ak.macro_china_agricultural_index)
    probe("macro_china_agricultural_product()", ak.macro_china_agricultural_product)
    probe("macro_china_vegetable_basket()", ak.macro_china_vegetable_basket)
    probe("macro_china_consumer_goods_retail()", ak.macro_china_consumer_goods_retail)
    probe("macro_china_cpi_yearly()", ak.macro_china_cpi_yearly)
    probe("macro_china_qyspjg()", ak.macro_china_qyspjg)
    probe("index_price_cflp()", ak.index_price_cflp)

    print("## 申万行业\n")
    probe("sw_index_first_info()", ak.sw_index_first_info)
    probe("sw_index_second_info()", ak.sw_index_second_info)
    probe("sw_index_third_info()", ak.sw_index_third_info)
    probe("sw_index_third_cons('801010')", ak.sw_index_third_cons, symbol="801010")
    probe(
        "index_hist_sw('801010','day')",
        ak.index_hist_sw,
        symbol="801010",
        period="day",
    )
    probe(
        "index_analysis_daily_sw('801010','day')",
        ak.index_analysis_daily_sw,
        symbol="801010",
        start_date="20230101",
        end_date="20260926",
    )
    probe("index_component_sw('801010')", ak.index_component_sw, symbol="801010")
    probe("index_realtime_sw('一级行业')", ak.index_realtime_sw, symbol="一级行业")

    print("## 上市公司\n")
    probe("stock_board_industry_cons_em('农林牧渔')", ak.stock_board_industry_cons_em, symbol="农林牧渔")
    probe("stock_profile_cninfo('000998')", ak.stock_profile_cninfo, symbol="000998")
    probe("stock_financial_abstract('000998')", ak.stock_financial_abstract, symbol="000998")
    probe(
        "stock_financial_analysis_indicator('000998','2021')",
        ak.stock_financial_analysis_indicator,
        symbol="000998",
        start_year="2021",
    )
    probe("stock_zygc_em('SZ000998')", ak.stock_zygc_em, symbol="SZ000998")
    probe("stock_individual_info_em('000998')", ak.stock_individual_info_em, symbol="000998")
    probe("stock_info_a_code_name()", ak.stock_info_a_code_name)
    probe(
        "stock_zh_a_disclosure_report_cninfo('000998')",
        ak.stock_zh_a_disclosure_report_cninfo,
        symbol="000998",
        market="沪深京",
        start_date="20230901",
        end_date="20260927",
    )
    probe("stock_fhps_detail_em('000998')", ak.stock_fhps_detail_em, symbol="000998")
    probe("stock_zh_a_gdhs_detail_em('000998')", ak.stock_zh_a_gdhs_detail_em, symbol="000998")
    probe("stock_share_change_cninfo('000998')", ak.stock_share_change_cninfo, symbol="000998")
    probe("stock_zh_a_hist('000998')", ak.stock_zh_a_hist, symbol="000998", period="daily", start_date="20230101", end_date="20260926", adjust="qfq")


if __name__ == "__main__":
    with contextlib.redirect_stdout(OUT), contextlib.redirect_stderr(sys.stderr):
        main()
    text = OUT.getvalue()
    with open("notes/akshare_probe.md", "w", encoding="utf-8") as fh:
        fh.write("# akshare 接口探测报告\n\n" + text)
    n_ok = text.count("STATUS: OK")
    n_fail = text.count("STATUS: **FAIL")
    print(f"probe written to notes/akshare_probe.md ; OK={n_ok} FAIL={n_fail}")
