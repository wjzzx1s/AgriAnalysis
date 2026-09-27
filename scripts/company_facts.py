#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""公司事实底稿的读取、校验与检索工具。

底稿目录 data/facts/<6 位代码>.yaml（格式见 data/facts/SCHEMA.md），
由公开资料检索得到，每条事实带来源 URL。本模块只做读取与结构化，
不生成任何文字；正文由 scripts/make_company_profiles.py 组合。

提供：
  load(code)                 读取一家公司的底稿 → Dossier
  load_all()                 读取全部底稿 → {code: Dossier}
  validate(dossiers)         结构校验（缺来源、空字段、字段名拼写）
  Dossier.financing_rows()   融资历史 → 表格行（时间/方式/规模/用途）
  Dossier.events(start,end)  取给定时间窗口内的事实条目（用于把股价阶段与公司事件对齐）
  Dossier.brief(n)           取最重要的 n 条事实（用于概述句）
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS_DIR = os.path.join(ROOT, "data", "facts")

# 底稿中的事实分区（顺序即叙述时的优先级）
SECTIONS = ["沿革", "主营与结构", "融资历史", "风险与困境", "战略与转型", "融资需求线索", "其他要点"]

# 视为“重大”的关键词：用于挑选概述句与事件标注
MAJOR_KEYS = ["重整", "预重整", "破产", "退市", "控制权", "易主", "借壳", "重组",
              "定增", "定向增发", "可转债", "公司债", "收购", "出售", "剥离", "跨界",
              "战略投资", "国资", "注资", "亏损", "商誉减值", "产能", "并购"]

_URL_RE = re.compile(r"^https?://", re.I)
_NOFIND = {"未查得", "未查到", "无", "暂未查得", "n/a", "N/A", ""}


@dataclass
class Item:
    """一条事实。时间字段可能是 时间（YYYY-MM-DD/YYYY-MM）、年（YYYY）或空。"""
    section: str
    text: str
    source: str = ""
    time: str = ""
    kind: str = ""       # 融资历史：方式
    scale: str = ""      # 融资历史：规模
    use: str = ""        # 融资历史：用途
    note: str = ""       # 融资历史：说明

    @property
    def year(self) -> int | None:
        m = re.search(r"(19|20)\d{2}", f"{self.time} {self.text}")
        return int(m.group(0)) if m else None

    @property
    def sort_key(self) -> tuple:
        t = str(self.time)
        m = re.match(r"((?:19|20)\d{2})[-/.]?(\d{2})?[-/.]?(\d{2})?", t)
        if m:
            y = int(m.group(1))
            mo = int(m.group(2) or 0)
            d = int(m.group(3) or 0)
            return (y, mo, d)
        return (0, 0, 0)

    @property
    def major(self) -> bool:
        s = f"{self.text} {self.kind}"
        return any(k in s for k in MAJOR_KEYS)


@dataclass
class Dossier:
    code: str
    name: str = ""
    position: str = ""
    items: list[Item] = field(default_factory=list)

    # ---------------------------------------------------------------- 访问器
    @property
    def ok(self) -> bool:
        return bool(self.items or self.position)

    def by_section(self, section: str) -> list[Item]:
        return [i for i in self.items if i.section == section]

    @property
    def 沿革(self) -> list[Item]:
        return self.by_section("沿革")

    @property
    def 融资历史(self) -> list[Item]:
        return sorted(self.by_section("融资历史"), key=lambda i: i.sort_key)

    @property
    def 风险与困境(self) -> list[Item]:
        return sorted(self.by_section("风险与困境"), key=lambda i: i.sort_key)

    @property
    def 战略与转型(self) -> list[Item]:
        return sorted(self.by_section("战略与转型"), key=lambda i: i.sort_key)

    @property
    def 融资需求线索(self) -> list[Item]:
        return sorted(self.by_section("融资需求线索"), key=lambda i: i.sort_key)

    @property
    def 其他要点(self) -> list[Item]:
        return self.by_section("其他要点")

    @property
    def 主营与结构(self) -> list[Item]:
        return self.by_section("主营与结构")

    def financing_rows(self) -> list[Item]:
        """融资历史中带方式/规模的行（用于出表）。"""
        return [i for i in self.融资历史 if i.kind or i.scale]

    def events(self, start=None, end=None, sections: list[str] | None = None) -> list[Item]:
        """取时间窗口内的事实（用于把股价阶段与公司事件对齐）。"""
        out = []
        for i in self.items:
            if sections and i.section not in sections:
                continue
            if i.section in ("其他要点",):
                continue
            y = i.year
            if y is None:
                continue
            if start is not None and y < start:
                continue
            if end is not None and y > end:
                continue
            out.append(i)
        return sorted(out, key=lambda i: i.sort_key)

    def brief(self, n: int = 2, prefer_major: bool = True) -> list[Item]:
        """挑最重要的 n 条事实。"""
        pool = [i for i in self.items if i.section in
                ("沿革", "主营与结构", "融资历史", "风险与困境", "战略与转型", "融资需求线索")]
        if prefer_major:
            maj = [i for i in pool if i.major]
            if len(maj) >= n:
                return sorted(maj, key=lambda i: i.sort_key)[-n:]
        return sorted(pool, key=lambda i: i.sort_key)[-n:]

    def has(self, *keywords: str) -> bool:
        blob = " ".join(i.text for i in self.items) + " " + self.position
        return any(k in blob for k in keywords)

    def find(self, *keywords: str) -> list[Item]:
        return [i for i in self.items if any(k in i.text for k in keywords)]


# ---------------------------------------------------------------- 读取
def _clean(s) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return "" if s in _NOFIND else s


def _items_from(raw, section: str) -> list[Item]:
    out: list[Item] = []
    if raw is None:
        return out
    if isinstance(raw, str):
        raw = [raw]
    for r in raw:
        if isinstance(r, str):
            out.append(Item(section=section, text=_clean(r)))
            continue
        if not isinstance(r, dict):
            continue
        text = _clean(r.get("事件") or r.get("事项") or r.get("要点") or r.get("说明")
                      or r.get("定位") or r.get("沿革"))
        out.append(Item(section=section, text=text,
                        source=_clean(r.get("来源") or r.get("来源URL") or r.get("url")),
                        time=_clean(r.get("时间") or r.get("年") or r.get("日期")),
                        kind=_clean(r.get("方式")), scale=_clean(r.get("规模")),
                        use=_clean(r.get("用途")), note=_clean(r.get("说明"))))
    return [i for i in out if i.text]


def load(code: str) -> Dossier:
    code = str(code).zfill(6)
    path = os.path.join(FACTS_DIR, f"{code}.yaml")
    if not os.path.exists(path):
        return Dossier(code=code)
    with open(path, encoding="utf-8") as fh:
        try:
            d = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:  # noqa: BLE001
            print(f"    [WARN] 底稿解析失败 {code}: {exc}")
            return Dossier(code=code)
    if not isinstance(d, dict):
        return Dossier(code=code)
    code_v = _clean(d.get("代码")) or code
    dos = Dossier(code=code_v.zfill(6), name=_clean(d.get("名称")),
                  position=_clean(d.get("定位")))
    for sec in SECTIONS:
        dos.items.extend(_items_from(d.get(sec), sec))
    return dos


def load_all() -> dict[str, Dossier]:
    out: dict[str, Dossier] = {}
    if not os.path.isdir(FACTS_DIR):
        return out
    for fn in sorted(os.listdir(FACTS_DIR)):
        if re.fullmatch(r"\d{6}\.yaml", fn):
            d = load(fn[:6])
            out[d.code] = d
    return out


def validate(dossiers: dict[str, Dossier]) -> list[str]:
    """结构校验：返回问题列表（缺定位、条目缺来源、来源不是 URL、区块为空）。"""
    problems: list[str] = []
    for code, d in dossiers.items():
        if not d.position:
            problems.append(f"{code} 缺“定位”")
        if not d.沿革:
            problems.append(f"{code} 缺“沿革”")
        srcs = 0
        for i in d.items:
            if not i.source:
                problems.append(f"{code} [{i.section}] 条目缺来源：“{i.text[:24]}”")
            elif not _URL_RE.match(i.source):
                problems.append(f"{code} [{i.section}] 来源不是 URL：“{i.source[:30]}”")
            else:
                srcs += 1
        if srcs == 0 and d.items:
            problems.append(f"{code} 无任何带 URL 的来源")
    return problems


if __name__ == "__main__":
    ds = load_all()
    print(f"底稿数：{len(ds)}")
    for code, d in ds.items():
        print(f"- {code} {d.name}: 定位={'有' if d.position else '缺'} "
              f"条目 {len(d.items)}（融资 {len(d.融资历史)}、风险 {len(d.风险与困境)}、"
              f"战略 {len(d.战略与转型)}）")
    probs = validate(ds)
    print(f"\n结构问题 {len(probs)} 条：")
    for p in probs[:60]:
        print(" -", p)
