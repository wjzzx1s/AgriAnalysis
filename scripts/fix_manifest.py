#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复/补全 data/raw/_manifest.json 的抓取清单。

背景：早期抓取脚本在清单损坏（多进程并发写同一 tmp 文件）时会重建清单，
而重跑 `fetch_*.py` 时已存在的文件被跳过、不再登记，
导致清单条目远少于实际数据文件（数据本身完整，缺的只是溯源记录）。

本脚本只做一件事：扫描 data/raw 下实际存在的文件，
把未登记的文件按“文件名约定 -> 接口名”映射后补入清单（含行数、列数、字节数与抓取时间），
已有条目一律保留不覆盖。可重复运行，幂等。
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MANIFEST, RAW  # noqa: E402

# 文件名 -> 接口（依据抓取脚本中的调用约定）
KIND_IFACE = {
    "profile": ("stock_profile_cninfo", "巨潮资讯网个股概况"),
    "basic": ("stock_zh_a_daily + stock_share_change_cninfo",
              "新浪日行情收盘价 × 流通股本估算流通市值"),
    "px": ("stock_zh_a_daily", "新浪财经日行情（2021 年至今）"),
    "fin_abstract": ("stock_financial_abstract", "新浪财经财务摘要（合并口径）"),
    "fin_ind": ("stock_financial_analysis_indicator", "新浪财经财务指标"),
    "share_chg": ("stock_share_change_cninfo", "巨潮资讯网股本变动"),
    "fhps": ("stock_dividend_cninfo", "巨潮资讯网分红送配"),
    "disc": ("stock_zh_a_disclosure_report_cninfo", "巨潮资讯网公告全文检索"),
    "zyjs": ("stock_zyjs_ths", "同花顺主营介绍"),
    "zygc": ("stock_zygc_em", "东方财富主营构成（旧版脚本产出，现流程不再抓取）"),
    "gdhs": ("stock_zh_a_gdhs", "东方财富股东户数（旧版脚本产出，现流程不再抓取）"),
}

PREFIX_IFACE = [
    ("fut_", "futures_main_sina / futures_inventory_em / futures_inventory_99",
     "新浪财经期货主力连续、东方财富仓单"),
    ("hog_", "futures_hog_spot_price 等（猪易数据）", "生猪现货价格指数与周度指标"),
    ("xt_", "futures_hog_core / futures_hog_cost / futures_hog_supply（玄田数据）",
     "生猪价格、成本与产能供给"),
    ("qh_spot", "spot_price_table_qh", "期货与现货价格对照"),
    ("macro_", "macro_china_* / cpi_*", "宏观、CPI 分项与产量进出口"),
    ("sw_", "sw_index_* / sw_index_cons", "申万行业指数、级别与成分股"),
]


def describe(path: str) -> tuple[int, int]:
    """返回 (行数, 列数)，CSV 用 pandas 探测，失败返回 (0, 0)。"""
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, nrows=5)
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            n = sum(1 for _ in fh) - 1
        return max(n, 0), len(df.columns)
    except Exception:  # noqa: BLE001
        return 0, 0


def interface_for(rel: str) -> tuple[str, str]:
    if rel.startswith("company/") or rel.startswith("company_legacy/"):
        kind = os.path.splitext(os.path.basename(rel))[0].split("_", 1)[-1]
        return KIND_IFACE.get(kind, ("（未知）", ""))
    for pref, iface, note in PREFIX_IFACE:
        if rel.startswith(pref):
            return iface, note
    return "（未映射）", ""


def main() -> None:
    man: dict = {}
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as fh:
                man = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] 现有清单不可读（{exc}），将从零重建")
            man = {}

    added, skipped, agg = 0, 0, {}
    for root, _dirs, files in os.walk(RAW):
        for fn in sorted(files):
            if not fn.endswith(".csv"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, RAW)
            st = os.stat(full)
            iface, note = interface_for(rel)
            if rel.startswith("company") and "/" in rel:
                kind = os.path.splitext(fn)[0].split("_", 1)[-1]
                a = agg.setdefault(kind, {"files": 0, "interface": iface,
                                          "note": note, "codes": []})
                a["files"] += 1
                a["codes"].append(os.path.splitext(fn)[0].split("_")[0])
                continue
            if rel in man:
                skipped += 1
                continue
            rows, cols = describe(full)
            man[rel] = {
                "interface": iface,
                "note": note,
                "rows": rows,
                "cols": cols,
                "bytes": st.st_size,
                "fetched_at": pd.Timestamp(st.st_mtime, unit="s",
                                           tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M"),
                "recovered": True,
            }
            added += 1

    for kind, a in sorted(agg.items()):
        key = f"company{'/legacy' if kind in ('zygc', 'gdhs') else ''}/*_{kind}.csv"
        man[key] = {
            "interface": a["interface"],
            "note": a["note"] + "（逐家抓取，每家一个文件）",
            "files": a["files"],
            "codes": sorted(set(a["codes"])),
            "recovered": True,
        }

    tmp = f"{MANIFEST}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, MANIFEST)
    print(f"清单条目：{len(man)}（新增 {added}，保留 {skipped}，"
          f"公司数据按 8 类聚合）\n→ {MANIFEST}")


if __name__ == "__main__":
    main()
