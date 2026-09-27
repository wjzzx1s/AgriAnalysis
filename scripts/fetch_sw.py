#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取申万行业分类：行业树、行业指数历史行情、行业成分股映射。

产出：
  data/raw/sw_l1_info.csv / sw_l2_info.csv / sw_l3_info.csv   行业信息（含估值）
  data/raw/sw_hist_<code>_<period>.csv                        行业指数历史（day / month）
  data/raw/sw_cons_<code>.csv                                 行业成分股
  data/clean/sw_stock_industry.csv                            股票 → 一/二/三级行业映射
"""
from __future__ import annotations

import sys
import time

import akshare as ak
import pandas as pd

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from common import CLEAN, exists, fetch, guard, load_raw, save  # noqa: E402

# 申万 2021 版：农林牧渔（一级 801010）下属二级与三级行业
L1 = {"801010": "农林牧渔"}
L2 = {
    "801011": "林业Ⅱ",
    "801012": "农产品加工",
    "801014": "饲料",
    "801015": "渔业",
    "801016": "种植业",
    "801017": "养殖业",
    "801018": "动物保健Ⅱ",
    "801019": "农业综合Ⅱ",
}
L3 = {
    "850111": "种子",
    "850112": "粮食种植",
    "850113": "其他种植业",
    "850114": "食用菌",
    "850121": "海洋捕捞",
    "850122": "水产养殖",
    "850131": "林业Ⅲ",
    "850142": "畜禽饲料",
    "850143": "水产饲料",
    "850144": "宠物食品",
    "850151": "果蔬加工",
    "850152": "粮油加工",
    "850154": "其他农产品加工",
    "850172": "生猪养殖",
    "850173": "肉鸡养殖",
    "850174": "其他养殖",
    "850181": "动物保健Ⅲ",
}
ALL = {**L1, **L2, **L3}


@guard("fetch_sw")
def main(force: bool = False):
    ok = fail = 0

    # 1) 行业信息表（含市盈率/市净率/成份个数）
    for fn, name in [(ak.sw_index_first_info, "sw_l1_info"),
                     (ak.sw_index_second_info, "sw_l2_info"),
                     (ak.sw_index_third_info, "sw_l3_info")]:
        if exists(name) and not force:
            ok += 1
            continue
        df = fetch(fn)
        if save(df, name, f"akshare: {fn.__name__}"):
            ok += 1
        else:
            fail += 1

    # 2) 行业指数历史行情（日频，用于周期与相关性；月频用于长周期）
    for code in ALL:
        for period in ("day", "month"):
            name = f"sw_hist_{code}_{period}"
            if exists(name) and not force:
                ok += 1
                continue
            df = fetch(ak.index_hist_sw, symbol=code, period=period)
            if save(df, name, f"akshare: index_hist_sw({code},{period})",
                    note=ALL[code]):
                ok += 1
            else:
                fail += 1
            time.sleep(0.3)

    # 3) 成分股
    for code in ALL:
        name = f"sw_cons_{code}"
        df = None
        if exists(name) and not force:
            df = load_raw(name)
            ok += 1
        else:
            df = fetch(ak.index_component_sw, symbol=code)
            if save(df, name, f"akshare: index_component_sw({code})", note=ALL[code]):
                ok += 1
            else:
                fail += 1
            time.sleep(0.3)

    # 4) 汇总映射表：股票 → 三级/二级/一级行业
    rows = []
    for code, lvl, mapping in (("801010", "一级", L1), ("801010", "二级", L2),
                               ("801010", "三级", L3)):
        pass
    for code, lvl in [(c, "三级") for c in L3] + [(c, "二级") for c in L2] + [(c, "一级") for c in L1]:
        df = load_raw(f"sw_cons_{code}")
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            rows.append({
                "股票代码": str(r["证券代码"]).zfill(6),
                "证券名称": r["证券名称"],
                "行业层级": lvl,
                "行业代码": code,
                "行业名称": ALL[code],
                "最新权重": r.get("最新权重"),
                "计入日期": r.get("计入日期"),
            })
    m = pd.DataFrame(rows)
    m.to_csv(f"{CLEAN}/sw_stock_industry.csv", index=False, encoding="utf-8-sig")
    print(f"    股票×行业映射 {len(m)} 行，覆盖 {m['股票代码'].nunique()} 只股票")

    print(f"[fetch_sw] ok={ok} fail={fail}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
