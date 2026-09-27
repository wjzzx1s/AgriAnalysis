#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐页检查 PDF 内容是否越出页边距（图片/表格 overfull 的机器化检查）。

版面为 A4、四边距 2.6cm。判定规则（留 0.35cm 的合理化余量）：
  左右：正文块之外 0.35cm 以外出现墨迹即报警（即距页边 < 2.25cm）；
  上：页眉占位，距页边 < 1.0cm 报警；下：页脚页码占位，距页边 < 1.0cm 报警。

用法：python3 scripts/check_margins.py main.pdf [dpi]
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

PDF = sys.argv[1] if len(sys.argv) > 1 else "main.pdf"
DPI = int(sys.argv[2]) if len(sys.argv) > 2 else 100
PT = 72.0
W_PT, H_PT = 595.28, 841.89
CM = PT / 2.54
MARGIN = 2.6                     # cm，正文边距
SLACK = 0.18                     # cm，容许的合理溢出
EDGE_TOP, EDGE_BOT = 1.0, 1.0    # cm，页眉/页脚占位

tmp = tempfile.mkdtemp(prefix="marginchk")
subprocess.run(["pdftoppm", "-r", str(DPI), "-png", PDF, os.path.join(tmp, "p")],
               check=True)
pages = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
print(f"pages={len(pages)} dpi={DPI} file={PDF}")

lim_l = (MARGIN - SLACK) * 10
lim_r = (MARGIN - SLACK) * 10
bad = []
worst = []
for i, f in enumerate(pages, 1):
    a = np.asarray(Image.open(os.path.join(tmp, f)).convert("L"))
    mask = a < 235
    if not mask.any():
        continue
    ys, xs = np.where(mask)
    h, w = a.shape
    s = w / W_PT
    left = xs.min() / s / CM * 10
    right = (W_PT - xs.max() / s) / CM * 10
    top = ys.min() / s / CM * 10
    bot = (H_PT - ys.max() / s) / CM * 10
    issues = []
    if left < lim_l:
        issues.append(f"左 {left:.1f}mm")
    if right < lim_r:
        issues.append(f"右 {right:.1f}mm")
    if top < EDGE_TOP * 10:
        issues.append(f"上 {top:.1f}mm")
    if bot < EDGE_BOT * 10:
        issues.append(f"下 {bot:.1f}mm")
    worst.append((min(left, right), i))
    if issues:
        bad.append((i, "、".join(issues)))

print(f"越界页数：{len(bad)}")
for i, why in bad:
    print(f"  p{i}: {why}")
worst.sort()
print("左右最窄的 8 页（mm，数值越小越靠近页边）：")
print("  " + ", ".join(f"p{i}={v:.1f}" for v, i in worst[:8]))
