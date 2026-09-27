#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探测：打印新浪资产负债表/现金流量表的全部列名（用于确定抓取白名单）。"""
import sys
import akshare as ak

code = sys.argv[1] if len(sys.argv) > 1 else "sz002124"
for kind in ("资产负债表", "现金流量表"):
    df = ak.stock_financial_report_sina(stock=code, symbol=kind)
    print(f"=== {kind} ({len(df.columns)} cols)")
    print(" | ".join(str(c) for c in df.columns))
    print()
