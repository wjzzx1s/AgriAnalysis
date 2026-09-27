#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""汇总第二部分（上市公司画像）正文所需的统计量，输出 notes/company_stats_h1.md。

口径：第二部分统一采用 **2026 年半年报**（合并报表、未年化；资产负债率为 2026 年
6 月末数值），2023---2025 年年报数据仅作为趋势对照。本脚本只读
data/clean/ 下由 make_company.py 与 make_company_profiles.py 产出的表，
不读原始接口，因此正文数字与附录表格永远同源。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CLEAN, NOTES  # noqa: E402

# 章节板块 → 申万三级行业（与 make_company.py 的 industry_groups 保持一致）
BLOCKS = {
    "种植业（第 8 章）": ["种子", "粮食种植", "其他种植业", "食用菌"],
    "养殖业（第 9 章）": ["生猪养殖", "肉鸡养殖", "其他养殖"],
    "饲料（第 10 章）": ["畜禽饲料", "水产饲料"],
    "动物保健（第 11 章）": ["动物保健Ⅲ", "动物保健"],
    "农产品加工（第 12 章）": ["粮油加工", "果蔬加工", "其他农产品加工"],
    "渔业、林业与宠物食品（第 13 章）": ["水产养殖", "海洋捕捞", "林业Ⅲ", "宠物食品"],
    "农业综合Ⅱ（第 13 章并入）": ["农业综合Ⅱ"],
}

OUT: list[str] = []


def w(s: str = "") -> None:
    OUT.append(s)


def n(x, nd: int = 2) -> str:
    try:
        v = float(x)
        return "—" if not np.isfinite(v) else f"{v:,.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def main() -> None:
    p = pd.read_csv(os.path.join(CLEAN, "company_profiles.csv"),
                    encoding="utf-8-sig").fillna({"三级": "未分类"})
    num_cols = ["流通市值亿元", "营收2026H1亿", "营收2026H1同比%", "归母2026H1亿",
                "归母2025H1亿", "ROE2026H1", "净利率2026H1", "毛利率2026H1",
                "负债率2026H1", "营收2025亿", "归母2025亿", "ROE2025",
                "负债率2025", "现金流2026H1亿"]
    for c in num_cols:
        p[c] = pd.to_numeric(p.get(c), errors="coerce")

    w("# 农业上市公司画像：正文统计数据（2026 年半年报口径）")
    w()
    w("由 `scripts/company_stats.py` 生成；正文数字均取自此文件，勿手工修改。")
    w("口径：财务数据为 2026 年半年报（合并报表、未年化），资产负债率为 2026 年 6 月末；")
    w("市值时点 2026-09-24；2023---2025 年年报数据仅作趋势对照。")
    w()
    w(f"样本：{len(p)} 家公司。")
    w()

    # ---------------------------------------------------------- 全样本概览
    h1_loss = int((p["归母2026H1亿"] < 0).sum())
    y_loss = int((p["归母2025亿"] < 0).sum())
    h1p_loss = int((p["归母2025H1亿"] < 0).sum())
    w("## 一、全样本概览")
    w()
    w(f"- 流通市值合计 {n(p['流通市值亿元'].sum(), 0)} 亿元，中位数 {n(p['流通市值亿元'].median(), 1)} 亿元，"
      f"最大 {n(p['流通市值亿元'].max(), 1)} 亿元")
    w(f"- 2026 年上半年：归母净利润合计 {n(p['归母2026H1亿'].sum(), 1)} 亿元，"
      f"亏损 {h1_loss} 家（{h1_loss / len(p) * 100:.1f}%），盈利 {len(p) - h1_loss} 家")
    w(f"- 2025 年上半年（对照）：归母净利润合计 {n(p['归母2025H1亿'].sum(), 1)} 亿元，亏损 {h1p_loss} 家")
    w(f"- 亏损公司的亏损额合计：2026H1 {n(p.loc[p['归母2026H1亿'] < 0, '归母2026H1亿'].sum(), 1)} 亿元，"
      f"2025H1 {n(p.loc[p['归母2025H1亿'] < 0, '归母2025H1亿'].sum(), 1)} 亿元")
    w(f"- 2026 年上半年营业收入合计 {n(p['营收2026H1亿'].sum(), 0)} 亿元，"
      f"营收同比中位数 {n(p['营收2026H1同比%'].median(), 1)}%")
    roe = p["ROE2026H1"].dropna()
    w(f"- 2026 年上半年 ROE（未年化）：中位数 {n(roe.median(), 2)}%，"
      f"为正 {int((roe > 0).sum())} 家、为负 {int((roe < 0).sum())} 家、缺失 {len(p) - len(roe)} 家；"
      f"超过 5%（约相当年化 10%）的 {int((roe > 5).sum())} 家")
    w(f"- 2025 年年报（对照）：亏损 {y_loss} 家，ROE 中位数 {n(p['ROE2025'].median(), 2)}%")
    d = p["负债率2026H1"]
    w(f"- 2026 年 6 月末资产负债率：中位数 {n(d.median(), 1)}%，"
      f"超过 65% 的 {int((d > 65).sum())} 家（其中亏损 {int(((d > 65) & (p['归母2026H1亿'] < 0)).sum())} 家）、"
      f"超过 80% 的 {int((d > 80).sum())} 家")
    w(f"- 2025 年末（对照）：负债率超过 65% 的 {int((p['负债率2025'] > 65).sum())} 家、"
      f"超过 80% 的 {int((p['负债率2025'] > 80).sum())} 家")
    _a, _b = p["归母2026H1亿"], p["归母2025H1亿"]
    w(f"- 2026 年上半年扭亏 {int(((_a > 0) & (_b < 0)).sum())} 家、"
      f"由盈转亏 {int(((_a < 0) & (_b > 0)).sum())} 家")
    # 两期对比的互斥分解（加总 = 104）：章节引用“盈利改善”家数时必须用这里的口径
    w(f"- 两期对比（互斥、合计 {len(p)} 家）：两期均盈利且同比改善 "
      f"{int(((_a > 0) & (_b > 0) & (_a > _b)).sum())} 家、两期均盈利但同比下滑 "
      f"{int(((_a > 0) & (_b > 0) & (_a <= _b)).sum())} 家、扭亏 {int(((_a > 0) & (_b < 0)).sum())} 家、"
      f"由盈转亏 {int(((_a < 0) & (_b > 0)).sum())} 家、两期均亏 {int(((_a < 0) & (_b < 0)).sum())} 家")
    w()

    # ---------------------------------------------------------- 分层
    w("## 二、潜在融资需求分层（第 14 章）")
    w()
    # 三档互不重复：按“补血—保壳—扩张”的顺序依次判定，公司只归入最紧迫的一档
    # （与 scripts/make_company_profiles.py 的 classify_tier 口径一致）
    t1 = p[(p["归母2026H1亿"] < 0) & (p["负债率2026H1"] > 65)]
    rest = p[~p.index.isin(t1.index)]
    _rg = pd.to_numeric(p.get("公告-重大重组与并购"), errors="coerce")
    t2 = rest[_rg.reindex(rest.index) >= 10]
    rest2 = rest[~rest.index.isin(t2.index)]
    t3 = rest2[(rest2["ROE2026H1"] > 5) & (rest2["负债率2026H1"] < 65)]
    w(f"- 第一档“补血型”（2026H1 亏损且 6 月末负债率 > 65%）：{len(t1)} 家，"
      f"其中负债率 > 80% 的 {int((t1['负债率2026H1'] > 80).sum())} 家，"
      f"2026 上半年亏损合计 {n(t1['归母2026H1亿'].sum(), 1)} 亿元；"
      f"2025 年报同口径为 {int(((p['归母2025亿'] < 0) & (p['负债率2025'] > 65)).sum())} 家")
    w(f"  - 名单：{'、'.join(f'{r.名称}（{n(r.负债率2026H1, 1)}%）' for r in t1.itertuples())}")
    w(f"- 第二档“保壳型”（重组并购公告 ≥ 10 条）：{len(t2)} 家，"
      f"其中 2026H1 亏损 {int((t2['归母2026H1亿'] < 0).sum())} 家")
    w(f"  - 名单：{'、'.join(t2['名称'].tolist())}")
    w(f"- 第三档“扩张型”（2026H1 ROE > 5% 且 6 月末负债率 < 65%）：{len(t3)} 家")
    w(f"  - 名单：{'、'.join(f'{r.名称}（ROE {n(r.ROE2026H1, 1)}%）' for r in t3.itertuples())}")
    both = p[(p["归母2026H1亿"] < 0) & (p["负债率2026H1"] > 65)
             & (_rg >= 10)]
    if len(both):
        w(f"- 两档标准同时命中的 {len(both)} 家（{'、'.join(both['名称'].tolist())}）"
          f"按“补血优先”计入第一档，故第二档为 {len(t2)} 家而非 {len(t2) + len(both)} 家")
    w()

    # ---------------------------------------------------------- 债务结构与滚动偿付压力
    w("## 二之二、债务结构与滚动偿付压力（2026 年 6 月末；第 14 章与附录表 \\ref{tab:company-financing} 的口径）")
    w()
    cash, sd = p["货币资金2026H1亿"], p["短期债务2026H1亿"]
    ibd, csr = p["有息负债2026H1亿"], p["现金短债比2026H1"]
    gap = (sd - cash).clip(lower=0)
    w(f"- 有息负债合计（短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券）："
      f"{n(ibd.sum(), 0)} 亿元；货币资金合计 {n(cash.sum(), 0)} 亿元")
    w(f"- 短期债务超过货币资金（现金短债比 < 1）的 {int((csr < 1).sum())} 家，"
      f"其中低于 0.5 的 {int((csr < 0.5).sum())} 家，无法计算（缺科目）的 {int(csr.isna().sum())} 家；"
      f"现金短债比中位数 {n(csr.median(), 2)}")
    w(f"- 以“短期债务 − 货币资金”衡量的静态缺口（仅计正值）：全样本合计 {n(gap.sum(), 0)} 亿元；"
      f"第一档 {len(t1)} 家合计 {n(gap.loc[t1.index].sum(), 0)} 亿元")
    w(f"  - 第一档：货币资金 {n(cash.loc[t1.index].sum(), 1)} 亿元 vs 短期债务 "
      f"{n(sd.loc[t1.index].sum(), 1)} 亿元、有息负债 {n(ibd.loc[t1.index].sum(), 1)} 亿元")
    w(f"- 2025 年全年“取得借款收到的现金”合计 {n(pd.to_numeric(p['取得借款2025亿'], errors='coerce').sum(), 0)} 亿元、"
      f"“偿还债务支付的现金”合计 {n(pd.to_numeric(p['偿还债务2025亿'], errors='coerce').sum(), 0)} 亿元")
    w()

    # ---------------------------------------------------------- 板块
    w("## 三、按章节板块的汇总")
    w()
    w("| 板块 | 公司数 | 流通市值（亿元） | 2026H1 营收（亿元） | 营收同比中位数 | "
      "2026H1 亏损家数 | 2026H1 ROE 中位数 | 6 月末负债率>65% | 2026H1 归母合计（亿元） | "
      "2025H1 归母合计（亿元） | 2025 年报亏损家数 |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for label, inds in BLOCKS.items():
        b = p[p["三级"].isin(inds)]
        w(f"| {label} | {len(b)} | {n(b['流通市值亿元'].sum(), 0)} | {n(b['营收2026H1亿'].sum(), 0)} | "
          f"{n(b['营收2026H1同比%'].median(), 1)}% | {int((b['归母2026H1亿'] < 0).sum())} | "
          f"{n(b['ROE2026H1'].median(), 2)}% | {int((b['负债率2026H1'] > 65).sum())} | "
          f"{n(b['归母2026H1亿'].sum(), 2)} | {n(b['归母2025H1亿'].sum(), 2)} | "
          f"{int((b['归母2025亿'] < 0).sum())} |")
    w()

    # ---------------------------------------------------------- 三级行业
    w("## 四、按申万三级行业（2026H1 ROE 中位数降序）")
    w()
    w("| 三级行业 | 公司数 | 2026H1 营收（亿元） | 营收同比中位数 | 2026H1 亏损家数 | "
      "2026H1 ROE 中位数 | 2026H1 ROE 平均 | 2025 ROE 中位数 | 6 月末负债率中位数 |")
    w("|---|---|---|---|---|---|---|---|---|")
    g = p.groupby("三级").agg(
        公司数=("代码", "count"),
        营收=("营收2026H1亿", "sum"),
        营收同比=("营收2026H1同比%", "median"),
        亏损=("归母2026H1亿", lambda s: int((s < 0).sum())),
        roe中位=("ROE2026H1", "median"),
        roe均值=("ROE2026H1", "mean"),
        roe2025中位=("ROE2025", "median"),
        负债率=("负债率2026H1", "median"),
    ).reset_index().sort_values("roe中位", ascending=False)
    for _, r in g.iterrows():
        w(f"| {r['三级']} | {int(r['公司数'])} | {n(r['营收'], 1)} | {n(r['营收同比'], 1)}% | "
          f"{int(r['亏损'])} | {n(r['roe中位'], 2)}% | {n(r['roe均值'], 2)}% | "
          f"{n(r['roe2025中位'], 2)}% | {n(r['负债率'], 1)}% |")
    w()

    # ---------------------------------------------------------- 逐公司
    w("## 五、逐公司关键数据")
    w()
    cols = ["代码", "名称", "三级", "流通市值亿元", "营收2026H1亿", "营收2026H1同比%",
            "归母2026H1亿", "归母2025H1亿", "ROE2026H1", "净利率2026H1", "毛利率2026H1",
            "负债率2026H1", "归母2025亿", "ROE2025", "负债率2025", "公告-再融资",
            "公告-重大重组与并购", "上市日期"]
    cols = [c for c in cols if c in p.columns]
    q = p[cols].sort_values("流通市值亿元", ascending=False)
    w("| " + " | ".join(cols) + " |")
    w("|" + "---|" * len(cols))
    for _, r in q.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (int, float, np.floating)):
                cells.append(n(v, 1) if "率" in c or "ROE" in c or "同比" in c else n(v, 2))
            else:
                cells.append(str(v))
        w("| " + " | ".join(cells) + " |")
    w()

    os.makedirs(NOTES, exist_ok=True)
    path = os.path.join(NOTES, "company_stats_h1.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"→ {path}（{len(OUT)} 行）")


if __name__ == "__main__":
    main()
