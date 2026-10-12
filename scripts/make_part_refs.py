#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为“第二部分”分册生成第一部分标签的桩文件（tex/gen/part1-refs.tex）。

背景：第二部分正文（第 7—15 章、附录 A/B、以及逐公司画像片段）会引用第一部分
章节（如“第 \\ref{sec:hog} 章”“第 \\ref{sec:soft} 章”）。第一部分不在该分册中，
但这些引用的编号必须照常印出。

最直接的做法是 xr-hyper 的 \\externaldocument{main}，但它会把 main.aux 里的
**全部**标签引入，其中包括第二部分自身的标签（sec:comp-overview 等），于是每次
编译都会报上百条 “Label ... multiply defined”。

本脚本改为“只补外部标签”：
  1) 从第二部分实际参与编译的源文件中收集所有 \\ref/\\pageref/\\nameref 的目标，
     减去这些文件中已定义的标签，得到“外部标签”集合；
  2) 从 main.aux 读取这些标签的编号与页码，生成 \\@ifundefined 保护的 \\newlabel 桩；
  3) 任何在 main.aux 里找不到的外部标签都报错退出（避免分册里印出 ??）。

用法：python scripts/make_part_refs.py
"""
from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUX = os.path.join(ROOT, "main.aux")
OUT = os.path.join(ROOT, "tex", "gen", "part1-refs.tex")

# 第二部分实际 \\input 的源文件（与 Makefile 的 PART2SRC 保持一致）
PART2_SRC = ["main-part2.tex", "tex/abstract-part2.tex",
             "tex/ch07-listed-overview.tex", "tex/ch08-planting.tex",
             "tex/ch09-breeding.tex", "tex/ch10-feed.tex",
             "tex/ch11-animal-health.tex", "tex/ch12-processing.tex",
             "tex/ch13-fishery-forestry.tex", "tex/ch14-strategy-financing.tex",
             "tex/ch15-conclusion.tex", "tex/appendix-a-sources.tex",
             "tex/appendix-b-companies.tex"]
PART2_GEN = ["tex/gen/comp_planting.tex", "tex/gen/comp_breeding.tex",
             "tex/gen/comp_feed.tex", "tex/gen/comp_vet.tex",
             "tex/gen/comp_processing.tex", "tex/gen/comp_fishery.tex",
             "tex/gen/comp_misc.tex", "tex/gen/company_master.tex",
             "tex/gen/company_by_ind.tex", "tex/gen/company_financing.tex"]
# 逐公司画像：第二部分特有的分组
PART2_PROFILES = ["planting", "breeding", "feed", "vet", "processing", "fishery", "misc"]

REF_RE = re.compile(r"\\(?:ref|pageref|nameref|autoref|eqref)\s*\{([^}]*)\}")
LBL_RE = re.compile(r"\\label\s*\{([^}]*)\}")
AUX_RE = re.compile(r"\\newlabel\{([^}]*)\}\{\{([^}]*)\}\{([^}]*)\}(?:\{([^}]*)\})?")


def sources() -> list[str]:
    out = []
    for p in PART2_SRC + PART2_GEN:
        f = os.path.join(ROOT, p)
        if os.path.exists(f):
            out.append(f)
        else:
            print(f"    [WARN] 缺少源文件：{p}")
    for g in PART2_PROFILES:
        out.extend(sorted(glob.glob(os.path.join(ROOT, "tex", "gen", "profiles", f"{g}.tex"))))
    return out


def main() -> int:
    if not os.path.exists(AUX):
        print(f"找不到 {AUX}：请先执行 make pdf（分册需要主报告已编译）")
        return 1
    refs: set[str] = set()
    labels: set[str] = set()
    for f in sources():
        t = open(f, encoding="utf-8").read()
        refs.update(m.group(1) for m in REF_RE.finditer(t))
        labels.update(m.group(1) for m in LBL_RE.finditer(t))
    ext = sorted(r for r in refs - labels if r and not re.match(r"^[A-Za-z]+$", r))
    aux = open(AUX, encoding="utf-8", errors="ignore").read()
    values: dict[str, tuple[str, str]] = {}
    for m in AUX_RE.finditer(aux):
        values[m.group(1)] = (m.group(2), m.group(3))
    missing = [k for k in ext if k not in values]
    if missing:
        print("以下外部标签在 main.aux 中找不到编号，分册会印出 ??：")
        for k in missing:
            print("   -", k)
        return 2

    lines = ["% 由 scripts/make_part_refs.py 生成 —— 勿手工修改。",
             "% 第二部分分册用到的第一部分标签（编号与页码取自 main.aux）。",
             "% 第二部分自身的标签不在此文件中，由本册正常定义，因此不会出现",
             "% “Label ... multiply defined” 警告。",
             "\\makeatletter"]
    for k in ext:
        val, page = values[k]
        lines.append(rf"\@ifundefined{{r@{k}}}{{\newlabel{{{k}}}{{{{{val}}}{{{page}}}}}}}{{}}")
    lines.append("\\makeatother")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    part1 = sum(1 for k in ext if k.startswith(("sec:", "fig:", "tab:")))
    print(f"[make_part_refs] 外部标签 {len(ext)} 条（{part1} 条为章节/图表）→ {os.path.relpath(OUT, ROOT)}")
    for k in ext:
        print(f"    {k} = {values[k][0]}（第 {values[k][1]} 页）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
