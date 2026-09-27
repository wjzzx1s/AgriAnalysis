#!/usr/bin/env python3
"""把一个公司的小节正文打印成纯文本，便于逐句审阅（只读，不改任何文件）。"""
import re
import sys
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def clean(blk: str) -> str:
    keep = []
    skip_env = ("addplot", "legend", "groupplot", "tikzpicture", "axis", "pgfplotsset",
                "adjustbox", "tabular", "longtable", "toprule", "midrule", "bottomrule",
                "caption", "label", "end{center}", "centering", "nextgroupplot", "pgfplots")
    for line in blk.split("\n"):
        st = line.strip()
        if st.startswith("\\") and any(k in st for k in skip_env):
            continue
        if st.startswith(("&", "i &", "- &")) or re.match(r"^(指标|营业收入|归母|毛利率|ROE|资产负债率|经营|货币资金|有息负债|现金短债)", st):
            continue
        keep.append(line)
    txt = "\n".join(keep)
    txt = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", "", txt)
    txt = txt.replace("\\%", "%").replace("---", "—")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt


def main(argv):
    codes = argv[1:]
    for f in sorted(glob.glob(os.path.join(ROOT, "tex/gen/profiles/*.tex"))):
        s = open(f, encoding="utf-8").read()
        for code in codes:
            i = s.find(f"（{code}）")
            if i < 0:
                continue
            head = s.rfind("\\subsubsection", 0, i)
            j = s.find("\\subsubsection", i)
            blk = s[head if head > 0 else i: j if j > 0 else i + 30000]
            print("=" * 78)
            print(clean(blk).strip())
            print()


if __name__ == "__main__":
    main(sys.argv)
