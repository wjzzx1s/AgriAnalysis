#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把调研子代理产出的补充事实（股权与控制权、经营要点、竞争优势、行业基本面）
合并进逐公司事实底稿 data/facts/<code>.yaml。

来源：/home/weiqi/.hermes/cache/scratch/agri_research/<code>.yaml（只含上述四个键）。
合并规则（幂等）：
  1) 每个条目必须有 http(s) 来源；缺来源、含省略号、写“未查得”的条目直接丢弃；
  2) 同一事项文本（归一化后）不重复收录；
  3) 底稿中已存在的同名区块先删除，再按 SECTIONS 的顺序插回原位，
     其余区块的文本与顺序保持不变（尽量少动已有 diff）。

用法：
  python scripts/merge_research.py            # 合并
  python scripts/merge_research.py --dry-run  # 只报告将要合并的条目数
"""
from __future__ import annotations

import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = os.path.join(ROOT, "data", "facts")
SRC = "/home/weiqi/.hermes/cache/scratch/agri_research"
NEW_KEYS = ["股权与控制权", "经营要点", "行业基本面", "竞争优势"]
# 新键插入到哪个已有键之后（保持底稿的可读顺序）
AFTER = {"股权与控制权": "沿革", "经营要点": "主营与结构",
         "行业基本面": "主营与结构", "竞争优势": "主营与结构"}
_URL = re.compile(r"^https?://", re.I)
_BAD = re.compile(r"……|\.\.\.|未查得|未查到")


def _norm(s: str) -> str:
    return re.sub(r"[\s，,。；;：:、（）()]+", "", str(s or ""))[:60]


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _clean(items) -> list[dict]:
    """过滤不合格条目，返回 [{事项, 来源}]。"""
    out: list[dict] = []
    seen: set[str] = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        text = str(it.get("事项") or it.get("事件") or it.get("要点") or "").strip()
        src = str(it.get("来源") or "").strip()
        if not text or not _URL.match(src) or _BAD.search(text):
            continue
        k = _norm(text)
        if k in seen:
            continue
        seen.add(k)
        out.append({"事项": re.sub(r"\s+", " ", text), "来源": src})
    return out


def _block(key: str, items: list[dict]) -> str:
    if not items:
        return f"{key}: []\n"
    txt = yaml.safe_dump({key: items}, allow_unicode=True, default_flow_style=False,
                         sort_keys=False, width=10 ** 6)
    # 与既有底稿的版式一致：嵌套列表缩进两格
    head, _, rest = txt.partition("\n")
    return head + "\n" + "\n".join(("  " + ln) if ln.strip() else ln for ln in rest.split("\n"))


def _drop_key(lines: list[str], key: str) -> tuple[list[str], int]:
    """从底稿文本行中删除某个顶层键的区块，返回（新行, 删除的条目数）。"""
    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", ln):
            start = i
            break
    if start is None:
        return lines, 0
    end = len(lines)
    for j in range(start + 1, len(lines)):
        # 顶层键：列 0、不含前导空白、不是列表项（底稿里列表项可能是 0 缩进的 "- 年: ..."）
        if (lines[j] and not lines[j][0].isspace()
                and not lines[j].lstrip().startswith("-")
                and re.match(r"^[^\s#][^:]*:", lines[j])):
            end = j
            break
    n = sum(1 for ln in lines[start + 1:end] if re.match(r"^\s*- ", ln))
    return lines[:start] + lines[end:], n


def _insert_after(lines: list[str], anchor: str, block: str) -> list[str]:
    """把区块插到某个顶层键之后；找不到锚点时追加到文件末尾。"""
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(anchor)}\s*:", ln):
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if (lines[j] and not lines[j][0].isspace()
                        and not lines[j].lstrip().startswith("-")
                        and re.match(r"^[^\s#][^:]*:", lines[j])):
                    end = j
                    break
            return lines[:end] + block.splitlines() + lines[end:]
    return lines + block.splitlines()


def merge(dry: bool = False) -> None:
    if not os.path.isdir(SRC):
        print(f"调研目录不存在：{SRC}")
        return
    n_files = n_add = n_src = 0
    for fn in sorted(os.listdir(SRC)):
        if not re.fullmatch(r"\d{6}\.yaml", fn):
            continue
        code = fn[:6]
        path = os.path.join(FACTS, fn)
        if not os.path.exists(path):
            print(f"    [WARN] 没有底稿：{code}")
            continue
        src = _load(os.path.join(SRC, fn))
        cur = _load(path)
        # 每键：底稿已有条目 + 调研新增条目，按事项文本去重（保留先出现的）
        uniq: dict[str, list[dict]] = {}
        for key in NEW_KEYS:
            seen: set[str] = set()
            items: list[dict] = []
            for it in _clean(cur.get(key)) + _clean(src.get(key)):
                k = _norm(it["事项"])
                if k in seen:
                    continue
                seen.add(k)
                items.append(it)
            if items:
                uniq[key] = items
            n_src += len(_clean(src.get(key)))
        if not uniq:
            continue
        added = sum(len(v) for v in uniq.values())
        old = sum(len(_clean(cur.get(k))) for k in NEW_KEYS)
        n_add += max(added - old, 0)
        n_files += 1
        if dry:
            continue
        lines = open(path, encoding="utf-8").read().split("\n")
        for key in NEW_KEYS:                       # 先删旧块，再按顺序插回
            lines, _ = _drop_key(lines, key)
        for key in NEW_KEYS:
            if key in uniq:
                lines = _insert_after(lines, AFTER[key], _block(key, uniq[key]))
        open(path, "w", encoding="utf-8").write("\n".join(lines))
    print(f"[merge_research] {'(dry-run) ' if dry else ''}覆盖底稿 {n_files} 家，"
          f"新增条目约 {n_add} 条（调研来源条目 {n_src} 条）")


if __name__ == "__main__":
    merge(dry="--dry-run" in sys.argv)
