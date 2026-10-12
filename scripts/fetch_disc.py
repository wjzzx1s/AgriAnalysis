#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""刷新巨潮公告清单到报告数据时点（2026-10-12），用于更新公告计数窗口。

原窗口为 2023-09-01---2026-09-27；本脚本把截止日延到 2026-10-12 并重写
data/raw/company/<code>_disc.csv（标题 + 时间 + 链接）。
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW, save  # noqa: E402
from fetch_companies import get_universe  # noqa: E402

SUB = "company"
START, END = "20230901", "20261012"


def one(code: str, name: str) -> tuple[str, int]:
    try:
        for attempt in range(4):          # 该接口对并发敏感：限流时返回非 JSON，需退避重试
            try:
                df = ak.stock_zh_a_disclosure_report_cninfo(symbol=code, market="沪深京",
                                                            start_date=START, end_date=END)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
        if df is None or not len(df):
            return code, 0

        keep = [c for c in ["代码", "简称", "公告标题", "公告时间", "公告链接"] if c in df.columns]
        save(df[keep], f"{code}_disc", f"巨潮资讯网 stock_zh_a_disclosure_report_cninfo({code})",
             note=name, subdir=SUB, force=True)
        return code, len(df)
    except Exception as exc:  # noqa: BLE001
        print(f"    [FAIL] {code} {name}: {type(exc).__name__} {str(exc)[:80]}")
        return code, -1


def main() -> None:
    uni = get_universe()
    total = 0
    with ThreadPoolExecutor(max_workers=1) as ex:
        futs = {ex.submit(one, r["股票代码"], r.get("证券名称", "")): r["股票代码"]
                for _, r in uni.iterrows()}
        done = 0
        for f in as_completed(futs):
            _, n = f.result()
            total += max(n, 0)
            done += 1
            if done % 20 == 0:
                print(f"  进度 {done}/{len(uni)} 公告合计 {total}")
            time.sleep(0.8)
    print(f"[fetch_disc] 完成，公告条目合计 {total}（窗口 {START}---{END}）")


if __name__ == "__main__":
    main()
