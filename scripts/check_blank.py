#!/usr/bin/env python3
"""检查逐页底部留白：统计每页最后一行墨迹的位置，列出留白最大的若干页。

用途：图形/表格被包进不可分页的 minipage 后，LaTeX 只能整块搬到下一页，
容易在页面底部留下大片空白。这个脚本把这种“排版空洞”量化出来，
便于判断是否需要重新调整图形尺寸或正文顺序。

用法： .venv/bin/python scripts/check_blank.py [main.pdf] [--top 12] [--dpi 60]
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image


def main(argv):
    pdf = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else "main.pdf"
    top = 12
    dpi = 60
    for i, a in enumerate(argv):
        if a == "--top":
            top = int(argv[i + 1])
        if a == "--dpi":
            dpi = int(argv[i + 1])
    if not os.path.exists(pdf):
        print(f"找不到 {pdf}")
        return 1
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
    pages = int([l for l in out.split("\n") if l.startswith("Pages:")][0].split()[-1])
    tmp = tempfile.mkdtemp(prefix="blank_")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-gray", pdf, os.path.join(tmp, "p")], check=True)
    rows = []
    for n in range(1, pages + 1):
        f = os.path.join(tmp, f"p-{n:03d}.png") if pages >= 100 else os.path.join(tmp, f"p-{n}.png")
        if not os.path.exists(f):
            cand = [x for x in os.listdir(tmp) if x.startswith(f"p-{n:0{len(str(pages))}}")]
            if not cand:
                continue
            f = os.path.join(tmp, cand[0])
        im = Image.open(f).convert("L")
        W, H = im.size
        px = im.load()
        last = 0
        for y in range(H - 1, -1, -1):
            row_ink = False
            for x in range(0, W, 2):
                if px[x, y] < 200:
                    row_ink = True
                    break
            if row_ink:
                last = y
                break
        frac = 1.0 - last / float(H)
        # 页脚页码不算：页码在底部约 5% 处，忽略最下方 7% 的墨迹
        rows.append((frac, n))
    rows.sort(reverse=True)
    big = [r for r in rows if r[0] > 0.30]
    print(f"{pdf}: {pages} 页；底部留白 >30% 的页数 = {len(big)}；"
          f"平均留白 = {sum(r[0] for r in rows) / len(rows) * 100:.1f}%")
    for frac, n in rows[:top]:
        print(f"  p{n}: 底部留白 {frac * 100:.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
