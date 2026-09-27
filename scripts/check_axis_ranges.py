#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查图表数据是否超出坐标轴范围（ymax/ymin 裁切 = 图形被截断）。

用法：.venv/bin/python scripts/check_axis_ranges.py
"""
import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def dat_range(path):
    try:
        df = pd.read_csv(path, sep=None, engine="python")
    except Exception:
        return None
    out = {}
    for c in df.columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().any():
            out[c] = (float(s.min()), float(s.max()))
    return out


def inline_series(text: str):
    """内联数据点：\\addplot ... coordinates {(x,y) ...} → [(行号, [(x,y), ...])]。

    内联 coordinates 的序列此前不被检查，曾漏掉一条整体落在 ymin 之下的曲线。
    """
    out = []
    for m in re.finditer(r"coordinates\s*\{", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        block = text[m.end():i - 1]
        pts = [(float(a), float(b)) for a, b in
               re.findall(r"\(\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*\)", block)]
        if pts:
            out.append((text[:m.start()].count("\n") + 1, pts))
    return out


def axis_range(lines, i, keys=("ymax", "ymin", "xmax", "xmin")):
    """从第 i 行（1 起）向上找所属 axis 的 xmin/xmax/ymin/ymax。"""
    got = {}
    for j in range(min(i, len(lines)) - 1, max(-1, i - 80), -1):
        for k in keys:
            if k not in got:
                m = re.search(rf"{k}\s*=\s*(-?[0-9.]+)", lines[j])
                if m:
                    got[k] = float(m.group(1))
        if ("begin{axis" in lines[j] or "nextgroupplot" in lines[j]
                or "begin{groupplot}" in lines[j]):
            break
    return got


def main():
    hits = []
    for tf in sorted(glob.glob("tex/ch*.tex")):
        text = open(tf, encoding="utf-8").read()
        lines = text.splitlines()

        # --- 内联 coordinates 序列
        for ln, pts in inline_series(text):
            rng = axis_range(lines, ln)
            ctx = " ".join(lines[max(0, ln - 80):ln])
            if "允许超出坐标范围" in ctx:
                continue
            prob = []
            ys = [y for _, y in pts]
            xs = [x for x, _ in pts]
            if "ymax" in rng and max(ys) > rng["ymax"] + 1e-9:
                prob.append(f"数据最大 {max(ys):.4g} > ymax {rng['ymax']:g}")
            if "ymin" in rng and min(ys) < rng["ymin"] - 1e-9:
                prob.append(f"数据最小 {min(ys):.4g} < ymin {rng['ymin']:g}")
            if "xmax" in rng and max(xs) > rng["xmax"] + 1e-9:
                prob.append(f"x 最大 {max(xs):.4g} > xmax {rng['xmax']:g}")
            if "xmin" in rng and min(xs) < rng["xmin"] - 1e-9:
                prob.append(f"x 最小 {min(xs):.4g} < xmin {rng['xmin']:g}")
            if prob:
                hits.append((tf, ln, "内联 coordinates", "; ".join(prob)))

        for i, l in enumerate(lines):
            m = re.search(r"table\[([^\]]*)\]\{(data/clean/[^}]+)\}", l)
            if not m:
                continue
            opts, path = m.group(1), m.group(2)
            if not os.path.exists(path):
                hits.append((tf, i + 1, path, "数据文件不存在"))
                continue
            dm = dat_range(path)
            if not dm:
                continue
            ymatch = re.search(r"y\s*=\s*([^,\]\s]+)", opts)
            ycol = ymatch.group(1) if ymatch else None
            # table[x index=0, y index=1] 形式：按列序号定位（避免把年份列当成数值列）
            xi = re.search(r"x index\s*=\s*(\d+)", opts)
            yi = re.search(r"y index\s*=\s*(\d+)", opts)
            cols = None
            try:
                cols = list(pd.read_csv(path, sep=None, engine="python", nrows=0).columns)
            except Exception:
                cols = None
            xidx = int(xi.group(1)) if xi else None
            yidx = int(yi.group(1)) if yi else None
            if cols and yidx is not None and yidx < len(cols):
                ycol = cols[yidx]
            ymax = ymin = None
            for j in range(i, max(-1, i - 60), -1):
                a = re.search(r"ymax\s*=\s*([0-9.]+)", lines[j])
                b = re.search(r"ymin\s*=\s*(-?[0-9.]+)", lines[j])
                if a and ymax is None:
                    ymax = float(a.group(1))
                if b and ymin is None:
                    ymin = float(b.group(1))
                if ("begin{axis" in lines[j] or "nextgroupplot" in lines[j]
                        or "begin{groupplot}" in lines[j] or "begin{semilogyaxis" in lines[j]):
                    break
            if ycol and ycol in dm:
                lo, hi = dm[ycol]
            elif yidx is not None:
                lo = hi = None
            else:
                cand = [v for k, v in dm.items() if k not in ("i", "x", "label")]
                if not cand:
                    continue
                lo, hi = min(c[0] for c in cand), max(c[1] for c in cand)
            # 数值列无法定位时不判定，避免把年份列当成数据列
            ctx = " ".join(lines[max(0, i - 60):i + 1])
            exempt = "允许超出坐标范围" in ctx        # 已人工确认并写入图注的例外
            prob = []
            if lo is not None and hi is not None and not exempt:
                if ymax is not None and hi > ymax + 1e-9:
                    prob.append(f"数据最大 {hi:.4g} > ymax {ymax:g}")
                if ymin is not None and lo < ymin - 1e-9:
                    prob.append(f"数据最小 {lo:.4g} < ymin {ymin:g}")
            # x 轴（多为时间轴）：数据超出 xmin/xmax 时曲线会被切断
            if "x" in dm and ycol is None:
                xlo, xhi = dm["x"]
                xmax = xmin = None
                for j in range(i, max(-1, i - 60), -1):
                    a = re.search(r"xmax\s*=\s*([0-9.]+)", lines[j])
                    b = re.search(r"xmin\s*=\s*([0-9.]+)", lines[j])
                    if a and xmax is None:
                        xmax = float(a.group(1))
                    if b and xmin is None:
                        xmin = float(b.group(1))
                    if ("begin{axis" in lines[j] or "nextgroupplot" in lines[j]
                            or "begin{groupplot}" in lines[j]):
                        break
                if xmax is not None and xhi > xmax + 1e-9:
                    prob.append(f"x 最大 {xhi:.4g} > xmax {xmax:g}")
                if xmin is not None and xlo < xmin - 1e-9:
                    prob.append(f"x 最小 {xlo:.4g} < xmin {xmin:g}")
            if prob:
                hits.append((tf, i + 1, f"{path} [{ycol}]", "; ".join(prob)))
    print(f"发现 {len(hits)} 处坐标范围裁切（图形会被截断）：")
    for f, ln, path, why in hits:
        print(f"  {f}:{ln}  {path}  ->  {why}")


if __name__ == "__main__":
    main()
