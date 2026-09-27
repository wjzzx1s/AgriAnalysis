#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把指定的逐公司片段抽出来拼成一个独立测试文档，用于快速检查图表版式。

用法：.venv/bin/python scripts/make_probe_tex.py 002124 000972 603336
产出：_probe.tex（仓库根目录，内含 preamble + 选中公司的画像片段）
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "tex", "gen", "profiles")


def blocks() -> dict[str, str]:
    """返回 {代码: 片段文本}。"""
    out: dict[str, str] = {}
    for fn in sorted(os.listdir(GEN)):
        if not fn.endswith(".tex"):
            continue
        txt = open(os.path.join(GEN, fn), encoding="utf-8").read()
        parts = re.split(r"(?m)^\\subsubsection\{", txt)
        for p in parts[1:]:
            m = re.search(r"\}\n\\label\{co:(\d{6})\}", p)
            if m:
                out[m.group(1)] = "\\subsubsection{" + p.rstrip() + "\n"
    return out


def main(codes: list[str]) -> None:
    bs = blocks()
    body = []
    for c in codes:
        c = str(c).zfill(6)
        if c not in bs:
            print(f"[WARN] 未找到 {c}")
            continue
        body.append(bs[c])
    tex = "\n".join([
        r"\documentclass[11pt, a4paper, fontset=none, zihao=-4]{ctexart}",
        # 与正式报告保持同样版心：否则探针的文本宽度更大，图形/表格越界问题查不出来
        r"\usepackage[top=2.6cm, bottom=2.6cm, left=2.6cm, right=2.6cm]{geometry}",
        r"\input{tex/preamble}",
        r"\begin{document}",
        r"\setcounter{section}{8}",
        r"\section{测试：逐公司画像版式}",
        r"\label{sec:probe}",
        "\n".join(body),
        r"\end{document}",
        "",
    ])
    path = os.path.join(ROOT, "_probe.tex")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(tex)
    print(f"→ {path}（{len(body)} 家公司）")


if __name__ == "__main__":
    main(sys.argv[1:] or ["002124", "000972", "603336"])
