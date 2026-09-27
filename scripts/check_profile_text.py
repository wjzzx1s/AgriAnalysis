#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""画像正文的文字自检：把“照抄公告 / 省略号 / 排版不统一”这类问题机检出来。

用法：.venv/bin/python scripts/check_profile_text.py [每类最多列出的条数]

检查对象是 tex/gen/profiles/*.tex 里 \pfl{...} 开头的正文段落（表格另计），逐家公司
（\subsubsection）定位，检查项：

1. 省略号：正文、表格里都不应出现“……”，出现即视为未完成句子；
2. 残句：句子收在“的/后/时/中/及/等/且/并/为/将/在/从/向/以/与/和”等连接词上；
3. 空括号、未配对引号、标点连用、重复词、中文与数字之间缺空格；
4. 公告搬运痕迹：文号、证券代码、公告编号、未闭合书名号等；
5. 段内重复：同一段落里出现两遍的 10 字以上实词片段（排除通用财务术语）；
6. 段落长度分布，用于检查“归纳提炼”后是否仍有过长段落。
"""
from __future__ import annotations

import glob
import os
import re
import sys

PROF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tex", "gen", "profiles")

ELL_RE = re.compile(r"……|…")
DANGLING_RE = re.compile(r"(?:(?<!型)(?<!性)(?<!类)的。|后。|时。|及。|且。|并。|为。|将。|在。|从。|向。|"
                         r"以。|与。|和。|或。|至。|自。|对。|把。|被。|是。|有。|由。|如。|"
                         r"(?<!之)(?<!当)(?<!其)(?<!国)中。|(?<!年)(?<!期)内。|(?<!应)(?<!针)对。|"
                         r"的；|后；|及；|等；|且；|并；|为；|与；|和。|后，|的，)$")
DUP_WORD_RE = re.compile(r"(公司公司|集团集团|融资融资|债债务|持股持股|股份股份|项目项目|"
                         r"的的|了了|年年末末|月月)")
PUNCT_RE = re.compile(r"[，,]{2,}|。{2,}|[；;]{2,}|[、]{2,}")
PAREN_RE = re.compile(r"（\s*）|\(\s*\)")
QUOTE_RE = re.compile(r"“|”")
MISS_SPACE_RE = re.compile(r"([\u4e00-\u9fff])([0-9A-Za-z])|([0-9A-Za-z])([\u4e00-\u9fff])")
BORROW_RE = re.compile(r"号文|证监许可|证券代码|本次检索|披露日期|公告编号|备查|／|"
                       r"《[^》]{0,40}$")
COMMON = ("筹资活动现金流净额", "经营活动现金流净额", "资产负债率", "归母净利润", "营业收入",
          "有息负债合计", "货币资金", "年化波动率", "申万农林牧渔指数", "全样本中位数",
          "三级行业", "短期债务", "长期债务", "现金短债比", "速动比率", "公司披露的风险",
          "近三年现金分红", "公开发行可转换", "发行股份及支付", "净资产收益率",
          "银行股份有限公司", "分行", "支行", "有限公司大连", "股份有限公司")
TEX_CMD_RE = re.compile(r"\\[a-zA-Z]+(\{[^}]*\})?")


def paragraphs(seg: str):
    """把一家公司的片段拆成（小节名, 段落正文, 表格文本）三元组。"""
    out = []
    for m in re.finditer(r"\\pfl\{([^}]*)\}(.*?)(?=\\pfl\{|\Z)", seg, re.S):
        body = m.group(2)
        tables = "\n".join(t.group(0) for t in
                           re.finditer(r"\\begin\{center\}.*?\\end\{center\}", body, re.S))
        prose = re.sub(r"\\begin\{center\}.*?\\end\{center\}", "", body, flags=re.S)
        out.append((m.group(1), prose.strip(), tables))
    return out


def main(limit: int = 8) -> int:
    files = sorted(glob.glob(os.path.join(PROF, "*.tex")))
    if not files:
        print("未找到 tex/gen/profiles/*.tex，请先执行 make profiles")
        return 1
    hits: dict[str, list[str]] = {}
    ell_prose = ell_table = 0
    paras = 0
    lens: list[int] = []

    def add(kind: str, where: str, snippet: str) -> None:
        hits.setdefault(kind, [])
        if len(hits[kind]) < limit * 6:
            hits[kind].append(f"{where} :: {snippet.strip()[:150]}")

    for f in files:
        text = open(f, encoding="utf-8").read()
        heads = list(re.finditer(r"\\subsubsection\{([^}]*)\}", text))
        for i, h in enumerate(heads):
            mc = re.search(r"（(\d{6})）", h.group(1))
            code = mc.group(1) if mc else "??????"
            seg = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            for sec, prose, tables in paragraphs(seg):
                paras += 1
                where = f"{os.path.basename(f)}[{code}]{sec}"
                plain = TEX_CMD_RE.sub(" ", prose)
                ell_prose += len(ELL_RE.findall(prose))
                ell_table += len(ELL_RE.findall(tables))
                lens.append(len(plain))
                if ELL_RE.search(prose):
                    add("正文省略号", where, ELL_RE.search(prose).group(0))
                if ELL_RE.search(tables):
                    add("表格省略号", where, ELL_RE.search(tables).group(0))
                for sent in re.split(r"(?<=[。；])", plain):
                    sent = sent.strip()
                    if sent and DANGLING_RE.search(sent):
                        add("残句", where, sent)
                for kind, rx in (("重复词", DUP_WORD_RE), ("标点连用", PUNCT_RE),
                                 ("空括号", PAREN_RE), ("公告搬运痕迹/全角斜杠", BORROW_RE)):
                    m = rx.search(plain)
                    if m:
                        add(kind, where, plain[max(0, m.start() - 20):m.end() + 20])
                if plain.count("“") != plain.count("”"):
                    add("引号不配对", where, f"“x{plain.count('“')} ”x{plain.count('”')}")
                ms = MISS_SPACE_RE.search(plain.replace("\\%", "%"))
                if ms:
                    add("中文与数字间缺空格", where, plain[max(0, ms.start() - 12):ms.end() + 12])
                chunks = [c for c in re.findall(r"[\u4e00-\u9fff]{10,}", plain) if c not in COMMON]
                seen: dict[str, int] = {}
                for ch in chunks:
                    for k in range(0, len(ch) - 10 + 1, 4):
                        seen[ch[k:k + 10]] = seen.get(ch[k:k + 10], 0) + 1
                rep = [k for k, v in seen.items() if v > 1 and not any(k in c or c in k for c in COMMON)]
                if rep:
                    add("段内重复片段", where, "；".join(rep[:3]))

    print(f"画像段落数：{paras}；正文省略号：{ell_prose}；表格内省略号：{ell_table}")
    if lens:
        lens.sort()
        print(f"段落长度：中位 {lens[len(lens) // 2]} 字，最短 {lens[0]}，最长 {lens[-1]}，"
              f"超过 700 字的段落 {sum(1 for x in lens if x > 700)} 个")
    print()
    if not hits:
        print("未发现上述问题。")
        return 0
    for kind, items in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        print(f"== {kind}（{len(items)} 例，最多显示 {limit} 例）")
        for it in items[:limit]:
            print("   -", it)
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8))
