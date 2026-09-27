#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""逐公司画像的正文撰写：把"事实底稿（data/facts/*.yaml）+ 财务/行情指标"组合成画像。

设计原则（对应"不得套用模板"的要求）：
  1) 每家公司的叙述由**自己的事实底稿**驱动：沿革、融资历史、风险事件、战略动作、
     融资需求线索决定该公司的重点与段落结构，而非固定句式填空；
  2) 数值全部来自数据管线（company_profiles.csv / *.dat），不手工填写；
  3) 句式按公司类型（重整型/困境型/扩张型/保壳型/稳健型）与公司代码派生的随机种子选择，
     同一句话不会在所有公司重复出现；
  4) 事实条目逐条标注来源（脚注形式放在段落末），正文不出现"资料来源"整行。

口径：财务以 2026 年半年报为当期（未年化），2023---2025 年年报作趋势对照；
有息负债 = 短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券 + 租赁负债。
"""
from __future__ import annotations

import random
import re

import numpy as np
import pandas as pd

from make_company import tex_escape
import company_charts as CH

H1 = "20260630"
H1_PREV = "20250630"
H1_CN = "2026 年半年报"
H1_END = "2026 年 6 月末"     # 资产负债表科目（时点）
H1_FLOW = "2026 年上半年"     # 利润表/现金流量表科目（期间）


# ------------------------------------------------------------------ 文本工具
def tesc(s) -> str:
    """事实底稿文本 → LaTeX 安全文本（底稿是纯文本，不含 LaTeX 命令）。"""
    s = str(s or "")
    s = s.replace("\\", "／")
    for a, b in (("%", r"\%"), ("&", r"\&"), ("#", r"\#"), ("_", r"\_"),
                 ("$", r"\$"), ("{", r"\{"), ("}", r"\}"),
                 ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def num_txt(v, nd=1) -> str:
    try:
        f = float(v)
        if not np.isfinite(f):
            return "—"
        return f"{f:,.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def pct_txt(v, nd=1) -> str:
    try:
        f = float(v)
        if not np.isfinite(f):
            return "—"
        return f"{f:.{nd}f}\\%"
    except (TypeError, ValueError):
        return "—"


def signed_pct(v, nd=1) -> str:
    try:
        f = float(v)
        if not np.isfinite(f):
            return "—"
        return f"{f:+.{nd}f}\\%"
    except (TypeError, ValueError):
        return "—"


def ym(ts) -> str:
    import pandas as pd
    try:
        t = pd.Timestamp(ts)
    except (TypeError, ValueError):
        return "—"
    return f"{t.year} 年 {t.month} 月"


def yi(v, nd=2) -> str:
    return num_txt(v, nd)


def get(r: dict, key: str, period: str):
    d = r.get(key)
    if isinstance(d, dict):
        return d.get(period, np.nan)
    return np.nan


def order_cn(n: int) -> str:
    r"""名次：交给导言区已加载的 zhnumber 宏渲染中文数字（第 \zhnumber{11} → 第十一）。"""
    if not n:
        return "—"
    return r"第\zhnumber{%d}位" % int(n)


def cut(s: str, n: int = 60, slack: int = 18) -> str:
    """摘录截断：优先切到 n 之后最近的标点（最多多取 slack 字），
    避免出现“1,850.0……”“支……”这类切在数字/词中间、读起来像坏掉的片段。"""
    s = str(s or "").strip().rstrip("。；;,.，")
    if len(s) <= n:
        return s
    at = max(s.rfind(ch, 0, n + slack) for ch in "；，、。：")
    if at < n // 2:                     # 附近没有标点，退化为硬截断
        at = n
    out = s[:at].rstrip("；，、。： ")
    out = re.sub(r"[-\u2011\d][\d,\.]*$", "", out).rstrip()   # 去掉末尾半截数字
    return out + "……"


# ------------------------------------------------------------------ 公司类型
def archetype(r: dict, d) -> str:
    debt = get(r, "负债率", H1)
    ni = get(r, "归母亿", H1)
    roe = get(r, "ROE", H1)
    risk = " ".join(i.text for i in d.风险与困境) + " " + d.position
    if re.search(r"重整|预重整|破产|退市风险警示", risk):
        return "reorg"
    if np.isfinite(ni) and ni < 0 and np.isfinite(debt) and debt > 80:
        return "distress"
    if np.isfinite(ni) and ni < 0 and np.isfinite(debt) and debt > 65:
        return "strapped"
    if np.isfinite(roe) and roe > 5 and np.isfinite(debt) and debt < 65:
        return "expansion"
    if "ST" in str(r.get("名称", "")):
        return "shell"
    return "steady"


ARCH_CN = {"reorg": "重整/预重整中的公司", "distress": "资产负债表紧张的公司",
           "strapped": "亏损且杠杆偏高的公司", "expansion": "扩张型公司",
           "shell": "风险警示类公司", "steady": "经营相对平稳的公司"}


# ------------------------------------------------------------------ 事实检索
def fact_brief(d, n=2, keys=("融资历史", "风险与困境", "战略与转型")):
    """挑出最值得写进正文的 n 条事实（优先重大事件，按时间倒序）。"""
    pool = [i for i in d.items if i.section in keys and i.text]
    maj = [i for i in pool if i.major]
    use = maj if len(maj) >= n else pool
    return sorted(use, key=lambda i: i.sort_key, reverse=True)[:n]


EVENT_RE = re.compile(r"收购|重整|重组|转让|上市|增发|配股|可转债|协议|控制权|变更|设立|签署|"
                      r"终止|解除|受理|处罚|冻结|出售|剥离|引入|认购|质押|增持|减持|定增|注入|"
                      r"募资|募集|并购|成立|投产|扩产|收购|和解|拍卖|退市")


def _ym_of(s) -> tuple[int, int] | None:
    m = re.match(r"\s*((?:19|20)\d{2})[-/.年]?\s*(\d{1,2})?", str(s or ""))
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2) or 0)
    except ValueError:
        return None


def events_in(d, t0, t1, sections=("融资历史", "风险与困境", "战略与转型", "融资需求线索"),
              t0_month: int = 0, t1_month: int = 12):
    """落在 [t0 年 t0_month 月, t1 年 t1_month 月] 内、且确属“事件型”的事实。"""
    out = []
    lo, hi = (t0, t0_month), (t1, t1_month)
    for i in d.events(start=t0, end=t1, sections=list(sections)):
        if not EVENT_RE.search(i.text):
            continue
        ym_ = _ym_of(i.time)
        if not ym_ or ym_[1] == 0:      # 需求精确到月
            continue
        if not (lo <= ym_ <= hi):
            continue
        out.append(i)
    return out


def facts_from(d, year: int, n: int = 3):
    return [i for i in d.items if i.year == year][:n]


def src_note(items) -> str:
    """正文不再逐段插脚注：来源统一在本小节末尾的“资料来源”清单里列出（见 src_block）。

    早期实现把 URL 放进逐段脚注，但百分号编码的链接（如百度百科词条）
    是一整段无法断行的 token，会顶出纸面（实测溢出到 601pt > 595pt 页宽），
    且一页堆十几个脚注严重影响阅读。现在改为：正文不留脚注，
    本节末尾输出“资料来源”清单（\tiny + 每 10 字符一个可断点）。
    """
    return ""


def src_block(urls: list[str]) -> str:
    """按用户要求：画像正文之后不再输出“资料来源”清单，本函数恒返回空串。

    来源链接并不丢失——它们仍逐条保存在 fact dossier（data/facts/<代码>.yaml）的
    source 字段里，需要核对时读 YAML 即可。保留函数与调用点是为了将来若恢复
    “小节末来源清单”，只需在这里把清单重新拼出来。
    """
    return ""


def _src_block_disabled(urls: list[str]) -> str:
    """（保留实现，当前不调用）小节末尾的“资料来源”清单。"""
    seen, uniq = set(), []
    for u in urls:
        u = re.split(r"[?#]", str(u).strip())[0][:96]
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    if not uniq:
        return ""
    def brk(u: str) -> str:
        parts = re.split(r"(/|\.|-|_|%|=|&)", u)
        out = []
        for k, piece in enumerate(parts):
            out.append(tesc(piece))
            if k % 2 == 1:
                out.append(r"\allowbreak{}")
            elif piece:
                chunked = [piece[j:j + 10] for j in range(0, len(piece), 10)]
                out[-1] = r"\allowbreak{}".join(chunked)
        return "".join(out)
    return "\n".join([
        r"\begin{center}",
        r"\begin{minipage}{\textwidth}\scriptsize\raggedright",
        r"\noindent\textbf{资料来源}\quad " +
        "；".join(rf"\texttt{{\tiny {brk(u)}}}" for u in uniq) + "。",
        r"\end{minipage}",
        r"\end{center}",
    ])
def para_basic(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    name = tesc(r["名称"])
    code = r["代码"]
    ind3 = tesc(r.get("三级") or "—")
    load = []

    # 沿革：成立年份与最初业务
    hist = d.沿革
    founded = None
    for i in hist:
        m = re.search(r"(19|20)\d{2}", f"{i.time} {i.text}")
        if m:
            founded = int(m.group(0))
            break
    opener = ""
    if founded and str(founded) not in (d.position or ""):
        opener = R.choice([
            f"{name}成立于 {founded} 年，",
            f"公司前身可追溯至 {founded} 年，",
            f"{founded} 年设立至今，{name}是",
        ])
    if d.position:
        load.append(f"{opener}{tesc(d.position)}{'' if d.position.endswith(('。', '）')) else '。'}")
    elif r.get("主营"):
        load.append(f"{opener}主营业务为“{tesc(cut(r['主营'], 60))}”，"
                    f"按申万行业分类（2021 版）归属三级行业“{ind3}”。")

    # 上市与股本、市值
    li = r.get("上市日期") or ""
    mkt = r.get("所属市场") or "A 股"
    shell = bool(re.search(r"(?<![不非未])借壳|重组上市|重大资产置换",
                           " ".join(i.text for i in d.沿革)))
    route = "通过重大资产重组（借壳）上市" if shell else "首发上市"
    seg = [f"公司于 {li} 在{mkt}{route}" if li else f"公司为{mkt}上市公司"]
    if np.isfinite(r.get("注册资本", np.nan)):
        seg.append(f"注册资本 {num_txt(r['注册资本'] / 1e4, 2)} 亿元")
    if np.isfinite(r.get("总股本亿股", np.nan)):
        seg.append(f"总股本 {num_txt(r['总股本亿股'], 2)} 亿股")
    load.append("，".join(seg) + "。")

    # 市值与行业地位
    cap = r.get("流通市值亿元", np.nan)
    rank, total = ctx["rank_cap"], ctx["n_ind"]
    seg = []
    if np.isfinite(cap):
        seg.append(f"截至 {r.get('行情日期') or '—'}收盘价 {num_txt(r.get('最新收盘'), 2)} 元，"
                   f"流通市值 {num_txt(cap, 1)} 亿元，近一年{signed_pct(r.get('近一年涨跌%'))}")
        if rank and total:
            seg.append(f"流通市值在三级行业“{ind3}”的 {total} 家公司中排{order_cn(rank)}")
    yoy = r.get("近一年涨跌%", np.nan)
    if np.isfinite(yoy) and np.isfinite(ctx["med"].get("yoy", np.nan)):
        m = ctx["med"]["yoy"]
        seg.append(f"近一年涨跌幅{'高于' if yoy > m else '低于'}全样本中位数"
                   f"（{signed_pct(m)}）{num_txt(abs(yoy - m), 1)} 个百分点")
    if seg:
        load.append("，".join(seg) + "。")

    # 主营构成（2026 年半年报 vs 2021 年年报）
    c = r.get("comp") or {}
    if c.get("ok"):
        items = "；".join(f"{tesc(k)} {num_txt(v, 1)}\\%" for k, v in c["新"] if np.isfinite(v))
        if items:
            unit = "行业" if "行业" in str(c.get("类别")) else "产品"
            # 分部收入含内部交易、未抵消至合并口径时可能超过 100%，
            # 写成“收入占比 131.1%”会显得荒谬，须改成“分部数据”并说明不可比
            _mx = max([v for _, v in c["新"] if np.isfinite(v)] or [0])
            if _mx > 100:
                load.append(f"按 {ctx['comp_period']}披露的{unit}分部数据（含内部交易、未抵消至合并口径）"
                            f"为{items}；该口径与合并营业收入不可直接比较。")
            else:
                load.append(f"按 {ctx['comp_period']}披露的{unit}构成，收入占比前三位为{items}。")
            if c.get("旧") and c.get("首位变化") and _mx <= 100:
                load.append(f"与 2021 年年报相比，第一大{unit}口径由“{tesc(c['旧'][0][0])}”（{num_txt(c['旧'][0][1], 1)}\\%）"
                        f"变为“{tesc(c['新'][0][0])}”（{num_txt(c['新'][0][1], 1)}\\%）；"
                        f"两期披露的分类口径有调整，占比差异中同时包含分类因素。")
    # 事实要点（沿革中后面的关键节点）
    notes = [i for i in hist[1:4] if i.text]
    if notes:
        load.append("发展过程中的关键节点包括：" +
                "；".join(f"{tesc(cut(n.text, 44))}（{tesc(str(n.time))}）" for n in notes[:3]) + "。")
    return " ".join(load) + src_note(notes[:3])


# ------------------------------------------------------------------ 2 历史股价
def para_price(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    load = []
    lead = R.choice([
        f"本报告样本区间（{ym(r['起月'])} 至 {ym(r['终月'])}）内，",
        f"自 {ym(r['起月'])}至 {ym(r['终月'])}，",
        f"以 {ym(r['起月'])}为起点、{ym(r['终月'])}为终点，",
    ])
    load.append(f"{lead}股价由 {num_txt(r['起价'], 2)} 元变为 {num_txt(r['终价'], 2)} 元，"
                f"累计 {signed_pct(r['区间涨跌'])}，"
                f"区间最高 {num_txt(r['高'], 2)} 元（{ym(r['高月'])}）、"
                f"最低 {num_txt(r['低'], 2)} 元（{ym(r['低月'])}）；"
                f"当前价相当于区间最高价的 {num_txt(r['终价'] / r['高'] * 100, 1)}\\%，"
                + (f"已接近区间最低价（{num_txt(r['终价'] / r['低'], 2)} 倍）。"
                   if r['终价'] / r['低'] <= 1.05 else
                   f"为区间最低价的 {num_txt(r['终价'] / r['低'], 2)} 倍。"))
    if np.isfinite(r.get("年化波动", np.nan)):
        seg = f"月度收益的年化波动率 {num_txt(r['年化波动'], 1)}\\%"
        mv = ctx["med"].get("vol", np.nan)
        if np.isfinite(mv):
            seg += (f"，{'高于' if r['年化波动'] > mv else '低于'}全样本中位数 "
                    f"{num_txt(mv, 1)}\\%")
        if ctx.get("rank_vol") and ctx.get("n_ind"):
            seg += (f"，在三级行业“{tesc(r.get('三级') or '—')}”的 {ctx['n_ind']} 家公司中"
                    f"波动率排{order_cn(ctx['rank_vol'])}")
        load.append(seg + "。")
    # 把关键的涨跌段与公司自己的事件对齐
    legs = r.get("legs")
    anchors = []
    if legs is not None and len(legs):
        for _, leg in legs.sort_values("幅度", key=lambda s: s.abs(), ascending=False).head(2).iterrows():
            ev = events_in(d, leg["起"].year, leg["止"].year,
                           t0_month=int(pd.Timestamp(leg["起"]).month),
                           t1_month=int(pd.Timestamp(leg["止"]).month))
            if ev:
                anchors.append((leg, ev[-1]))
    if anchors:
        txt = "；".join(
            f"{ym(l['起'])} 至 {ym(l['止'])}的{'上涨' if l['幅度'] > 0 else '下跌'}"
            f"（{signed_pct(l['幅度'])}）与公司{tesc(cut(e.text, 38))}"
            f"（{tesc(str(e.time))}）在时间上重合"
            for l, e in anchors[:2])
        load.append("从事件看，" + txt + "——股价的拐点多数能在公司自身的资本运作与风险事件上找到对应。")
        cites = [e for _, e in anchors]
    else:
        cites = []
        if np.isfinite(r.get("rho_ind", np.nan)):
            load.append(f"区间内股价与申万农林牧渔指数的月度收益相关系数为 {r['rho_ind']:+.2f}，"
                        f"走势更多由板块整体与农产品价格而非公司个体事件驱动。")
    return " ".join(load) + src_note(cites)


# ------------------------------------------------------------------ 3 过去周期分析
def para_cycle(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    load = [f"以 {int(ctx['zz'] * 100)}\\% 的 ZigZag 阈值划分，样本区间内股价形成 "
            f"{r['nup']} 个主升段与 {r['ndn']} 个主跌段。"]
    up, dn = r.get("最大涨"), r.get("最大跌")
    order = R.choice([0, 1]) if (up is not None and dn is not None) else 0
    def up_txt():
        return (f"最大主升段出现在 {ym(up['起'])} 至 {ym(up['止'])}，"
                f"{up['月数']:.0f} 个月{signed_pct(up['幅度'])}")
    def dn_txt():
        return (f"最大主跌段为 {ym(dn['起'])} 至 {ym(dn['止'])}，"
                f"{dn['月数']:.0f} 个月{signed_pct(dn['幅度'])}")
    if up is not None and dn is not None:
        load.append((up_txt() if order == 0 else dn_txt()) + "；" +
                    (dn_txt() if order == 0 else up_txt()) + "。")
    elif up is not None:
        load.append(up_txt() + "。")
    elif dn is not None:
        load.append(dn_txt() + "。")
    last = r.get("末段")
    if last is not None:
        load.append(
            f"最近一次转折出现在 {ym(last['止'])}"
            f"（{last['方向']}段自 {ym(last['起'])}起，{last['月数']:.0f} 个月"
            f"{signed_pct(last['幅度'])}），当前处于该段{'的延续之中' if last['方向'] == '下跌' else '之后的震荡之中'}。")
    # 与行业指数见底时间的先后
    lag = ctx.get("lag_vs_index")
    if lag is not None:
        if lag > 1:
            load.append(f"与申万农林牧渔指数的最近一次底部相比，该公司见底晚约 {lag} 个月，"
                        f"在本轮下行中属于调整更慢的一类。")
        elif lag < -1:
            load.append(f"公司股价较申万农林牧渔指数提前约 {abs(lag)} 个月见底，"
                        f"是板块中较早定价周期反转的公司之一。")
        else:
            load.append("公司股价与申万农林牧渔指数几乎同步见底，个股并未走出独立行情。")
    # 相关性
    if np.isfinite(r.get("rho_ind", np.nan)):
        s = f"与申万农林牧渔指数的月度收益相关系数 {r['rho_ind']:+.2f}"
        if np.isfinite(r.get("rho_hog", np.nan)):
            s += f"、与生猪现货价格的相关系数 {r['rho_hog']:+.2f}"
        load.append(s + "。")
    # 行业与公司自身周期解释（按公司类型与主营写）
    load.append(ctx["cycle_note"])
    cites = ctx.get("cycle_cites") or []
    return " ".join(load) + src_note(cites)


# ------------------------------------------------------------------ 4 盈利情况
def para_profit(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    e, f = get(r, "营收亿", H1), get(r, "归母亿", H1)
    ep, fp = get(r, "营收亿", H1_PREV), get(r, "归母亿", H1_PREV)
    a, b = get(r, "营收亿", "20231231"), get(r, "营收亿", "20251231")
    na, nb = get(r, "归母亿", "20231231"), get(r, "归母亿", "20251231")
    load = []
    if np.isfinite(e):
        s = f"{H1_FLOW}营业收入 {yi(e)} 亿元"
        if np.isfinite(ep) and ep > 0:
            s += f"（同比 {signed_pct((e / ep - 1) * 100)}）"
        load.append(s + "，")
        if np.isfinite(f):
            t = f"归母净利润 {yi(f)} 亿元"
            if np.isfinite(fp):
                if fp > 0 and f <= 0:
                    t += "，由上年同期的盈利转为亏损"
                elif fp < 0 and f > 0:
                    t += "，实现扭亏"
                elif fp < 0 and f < 0:
                    t += "，亏损同比" + ("收窄" if abs(f) < abs(fp) else "扩大") + \
                         f" {num_txt(abs(abs(f) - abs(fp)), 2)} 亿元"
                elif fp > 0 and f > 0:
                    t += f"，同比 {signed_pct((f / fp - 1) * 100)}"
            load[-1] += t + "。"
        else:
            load[-1] += "归母净利润数据缺失。"
    load.append(f"以年报为趋势对照，2023---2025 年营业收入由 {yi(a)} 亿元变为 {yi(b)} 亿元"
                f"（两年年均复合增速 {signed_pct(((b / a) ** 0.5 - 1) * 100) if np.isfinite(a) and np.isfinite(b) and a > 0 else '—'}），"
                f"归母净利润由 {yi(na)} 亿元变为 {yi(nb)} 亿元。")
    roe, npr, gpr = get(r, "ROE", H1), get(r, "净利率", H1), get(r, "毛利率", H1)
    seg = (f"按半年报口径，{H1_FLOW}的 ROE 为 {num_txt(roe, 1)}\\%（未年化）、"
           f"销售净利率 {num_txt(npr, 1)}\\%、毛利率 {num_txt(gpr, 1)}\\%")
    rank_roe, n_ind = ctx["rank_roe"], ctx["n_ind"]
    if rank_roe and n_ind and np.isfinite(roe):
        seg += (f"，ROE 在“{tesc(r.get('三级') or '—')}”{n_ind} 家公司中"
                f"按数值由高到低排{order_cn(rank_roe)}")
    load.append(seg + "。")
    # 与行业中位数比较（行业值必须用同一口径的三级行业中位数，不能用全样本中位数冒充）
    med_roe = ctx["med"].get("roe", np.nan)
    if np.isfinite(roe) and np.isfinite(med_roe):
        gap = roe - med_roe
        choices = []
        med_ind = ctx.get("med_ind_roe", float("nan"))
        if np.isfinite(med_ind):
            g_ind = roe - med_ind
            choices.append(
                f"按同一口径，三级行业“{tesc(r.get('三级') or '—')}”{ctx.get('n_ind')} 家公司的半年 ROE 中位数为 "
                f"{num_txt(med_ind, 2)}\\%，该公司{'高于' if g_ind > 0 else '低于'}其中位数 "
                f"{num_txt(abs(g_ind), 2)} 个百分点。")
        choices.append(
            f"同期全样本半年 ROE 中位数 {num_txt(med_roe, 2)}\\%，公司与之相差 "
            f"{num_txt(abs(gap), 2)} 个百分点（{'略好于' if gap > 0 else '弱于'}中位数公司）。")
        load.append(R.choice(choices))
    # 亏损/盈利的成因（来自事实底稿，缺失时不强加解释）
    rev_txt, ni_txt = f"{e:.2f}" if np.isfinite(e) else None, f"{abs(f):.2f}" if np.isfinite(f) else None
    cause = []
    for i in d.items:
        if i.section not in ("风险与困境", "战略与转型", "主营与结构"):
            continue
        if not re.search(r"亏损|减值|计提|停产|出栏|价格|成本|疫情|火灾|诉讼|重整|下滑|下降|减少", i.text):
            continue
        if rev_txt and rev_txt in i.text and ni_txt and ni_txt in i.text:
            continue      # 只是复述当期数字，不构成成因
        # 年报口径的“实现营业收入 … 归属于上市公司股东的净利润 …”是数据复述，
        # 与上面的表格重复，且不含成因；只有在提到原因/减值/价格等驱动时才保留
        if (re.search(r"实现营业收入|全年营业收入", i.text)
                and re.search(r"归属于上市公司股东的净利润|归母净利润", i.text)
                and not re.search(r"原因|由于|受|导致|拖累|影响|减值|计提|停产|疫情|火灾|重整", i.text)):
            continue
        cause.append(i)
    cause = sorted(cause, key=lambda i: i.sort_key, reverse=True)[:2]
    if cause:
        # 事实条目常以“公司披露拟…”开头，再加“结合公司披露，”就成了“公司披露…公司披露…”
        lead = R.choice(["结合公司披露，", "公司公告显示，", "从公开披露看，", "公告披露的信息包括："])
        if cause[0].text.startswith(("公司", "拟", "因", "受", "本")):
            lead = ""
        load.append(lead + "；".join(tesc(cut(i.text, 52)) for i in cause) + "。")
    cites = cause
    return " ".join(x for x in load if x) + src_note(cites)


# ------------------------------------------------------------------ 5 财务分析
def para_finance(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    load = []
    dbt = get(r, "负债率", H1)
    d25 = get(r, "负债率", "20251231")
    d23 = get(r, "负债率", "20231231")
    s = f"{H1_END}资产负债率 {num_txt(dbt, 1)}\\%"
    base = d25 if np.isfinite(d25) else d23
    if np.isfinite(base) and np.isfinite(dbt):
        y = "2025 年末" if np.isfinite(d25) else "2023 年末"
        ch = dbt - base
        s += f"，较 {y} {'上升' if ch >= 0 else '下降'} {num_txt(abs(ch), 1)} 个百分点"
    med_debt = ctx["med"].get("debt", np.nan)
    if np.isfinite(med_debt) and np.isfinite(dbt):
        s += f"（样本中位数 {num_txt(med_debt, 1)}\\%，所处三级行业内按由低到高排{order_cn(ctx['rank_debt'])}）"
    load.append(s + "。")
    # 偿债与债务结构（资产负债表口径）
    cash = get(r, "货币资金亿", H1)
    st = get(r, "短期债务亿", H1)
    ibd = get(r, "有息负债亿", H1)
    lt = get(r, "长期债务亿", H1)
    csr = get(r, "现金短债比", H1)
    if np.isfinite(cash) and np.isfinite(st) and st > 0:
        tone = ("覆盖充分" if csr and csr >= 1 else "覆盖偏紧" if csr and csr >= 0.3 else "缺口明显")
        load.append(f"{H1_END}货币资金 {yi(cash)} 亿元、短期债务（短期借款与一年内到期非流动负债）"
                    f"{yi(st)} 亿元、长期债务 {yi(lt)} 亿元，有息负债合计 {yi(ibd)} 亿元，"
                    f"现金短债比 {num_txt(csr, 2)} 倍——{tone}。")
        if np.isfinite(ibd) and np.isfinite(cash):
            net = ibd - cash
            rev_h1 = get(r, "营收亿", H1)
            na = get(r, "净资产亿", np.nan)
            if np.isfinite(rev_h1) and rev_h1 > 0:
                tail = f"相当于其 2026 年上半年营业收入的 {num_txt(net / rev_h1 * 100, 0)}\\%。"
            elif np.isfinite(na):
                tail = f"而期末归母净资产仅 {yi(na)} 亿元。"
            else:
                tail = "对应期末归母净资产规模有限。"
            load.append(f"净有息负债 {yi(net)} 亿元，{tail}")
    # 短期偿债与营运
    if np.isfinite(r.get("流动比率", np.nan)):
        load.append(f"流动比率 {num_txt(r['流动比率'], 2)}、速动比率 {num_txt(r.get('速动比率'), 2)}，"
                    + ("短期偿付压力较大" if r["流动比率"] < 1 else "短期指标尚可") +
                    (f"；存货周转天数 {num_txt(r.get('存货天数'), 0)} 天、"
                     f"应收账款周转天数 {num_txt(r.get('应收天数'), 0)} 天。" if np.isfinite(r.get("存货天数", np.nan)) else "。"))
    # 经营现金流
    cf, ni = get(r, "现金流亿", H1), get(r, "归母亿", H1)
    if np.isfinite(cf):
        if np.isfinite(ni) and ni > 0 and cf > 0:
            t = "经营现金流与利润同向为正，内生资金可以支撑运营"
        elif np.isfinite(ni) and ni < 0 and cf > 0:
            t = "净利润为负而经营现金流为正，差额主要来自折旧摊销与营运资本变动，说明亏损尚未完全转化为现金流出"
        elif np.isfinite(ni) and ni > 0 and cf <= 0:
            t = "净利润为正但经营现金流为负，利润的现金含量偏低"
        else:
            t = "经营现金流与利润同时为负，" + ("日常运营对债务与股东投入的依赖度较高" if ctx["arch"] != "steady"
                                        else "现金消耗较快")
        load.append(f"{H1_FLOW}经营活动现金流净额 {yi(cf)} 亿元，{t}。")
    # 投资强度（在建工程）
    cip, cip25 = get(r, "在建工程亿", H1), get(r, "在建工程亿", "20251231")
    if np.isfinite(cip) and cip > 0.5:
        ch = (cip - cip25) if np.isfinite(cip25) else np.nan
        load.append(f"{H1_END}在建工程 {yi(cip)} 亿元"
                    + (f"，较上年末{'增加' if ch > 0 else '减少'} {yi(abs(ch))} 亿元"
                       f"，{'仍有在建投入' if ch > 0 else '在建投入在收缩'}" if np.isfinite(ch) else "")
                    + "。")
    # 商誉
    gw, net_asset = r.get("商誉亿", np.nan), r.get("净资产亿", np.nan)
    if np.isfinite(gw) and gw > 1:
        t = (f"{H1_END}商誉 {yi(gw)} 亿元，占归母净资产的 {num_txt(gw / net_asset * 100, 1)}\\%，"
             f"是净资产中最脆弱的一块" if np.isfinite(net_asset) and net_asset > 0 else
             f"{H1_END}商誉 {yi(gw)} 亿元")
        load.append(t + "。")
    # 事实中的财务风险（审计意见、净资产为负、诉讼冻结等）
    SEV = [r"净资产为负|资不抵债|退市风险", r"重整|破产", r"违约|逾期|冻结|失信",
           r"立案|处罚|问询函", r"诉讼|仲裁", r"质押|减持"]
    risks = [i for i in d.风险与困境 if re.search("|".join(SEV), i.text)]
    def sev(i):
        for k, pat in enumerate(SEV):
            if re.search(pat, i.text):
                return k
        return len(SEV)
    risks = sorted(risks, key=lambda i: (sev(i), -i.sort_key[0]))[:2]
    if risks:
        load.append("公司披露的财务与合规风险包括：" +
                    "；".join(tesc(cut(i.text, 44)) for i in risks) + "。")
    return " ".join(x for x in load if x) + src_note(risks)


# ------------------------------------------------------------------ 6 重大战略转型
def para_strategy(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    ev = r["events"]["ev"]
    items = d.战略与转型
    load = []
    if items:
        shown = items[-4:] if len(items) > 4 else items
        lead = R.choice([
            f"公司在报告期内的战略动作可归为 {len(shown)} 项：",
            f"从公开披露看，公司的战略推进包括：",
            f"近三年公司的战略动作集中在以下几个方面：",
        ])
        load.append(lead + "；".join(
            (f"{tesc(str(i.time))} " if i.time else "") + tesc(cut(i.text, 56))
            for i in shown) + "。")
    # 并购与重组公告计数（数据侧的事实）
    load.append(f"公告口径上，近三年（2023 年 9 月---2026 年 9 月）公司披露重大重组与并购类公告 "
                f"{ev.get('重大重组与并购', 0)} 条、对外投资与转型类公告 {ev.get('对外投资与转型', 0)} 条、"
                f"回购与股权激励类公告 {ev.get('回购与激励', 0)} 条，"
                f"合计公告 {r['events']['n']} 条。")
    # 主营结构变化
    c = r.get("comp") or {}
    if c.get("ok") and c.get("旧"):
        unit = "行业" if "行业" in str(c.get("类别")) else "产品"
        old, new = c["旧"][0], c["新"][0]
        _share_ok = np.isfinite(new[1]) and np.isfinite(old[1]) and new[1] <= 100 and old[1] <= 100
        if c.get("首位变化") and _share_ok:
            load.append(f"主营结构的口径变化已经落到报表上：2021 年年报的第一大{unit}为"
                        f"“{tesc(old[0])}”（{num_txt(old[1], 1)}\\%），"
                        f"{ctx['comp_period']}为“{tesc(new[0])}”（{num_txt(new[1], 1)}\\%）；"
                        f"公司在这两期的分部划分方式有过调整。")
        elif _share_ok and np.isfinite(c.get("首位占比变化", np.nan)) and abs(c["首位占比变化"]) >= 10:
            load.append(f"第一大{unit}“{tesc(new[0])}”的收入占比由 2021 年年报的 "
                        f"{num_txt(old[1], 1)}\\% 变为 {num_txt(new[1], 1)}\\%"
                        f"（{num_txt(abs(c['首位占比变化']), 1)} 个百分点），收入结构出现再平衡。")
        else:
            _w = ("分部口径的收入（含内部交易）" if not _share_ok else "收入占比")
            load.append(f"第一大{unit}仍是“{tesc(new[0])}”，{_w} {num_txt(new[1], 1)}\\%，"
                        f"与 2021 年年报相比没有方向性变化。")
    # 结论句：按类型给不同的判断
    trans = bool(items) or c.get("首位变化") or (ev.get("重大重组与并购", 0) >= 5)
    if ctx["arch"] == "reorg":
        load.append("综合判断，公司当前的战略重心不是扩张而是化解债务与完成重整，"
                    "业务层面的调整让位于司法重整程序。")
    elif "ST" in str(r["名称"]):
        load.append("公司证券简称带风险警示标识，报告期内的资本运作以维持上市地位为主线，"
                    "属于第 \\ref{sec:financing-strategy} 节界定的“跨界与保壳”路径。")
    elif trans:
        load.append("综合判断，公司在报告期内有明确的外延扩张或业务结构调整动作，"
                    "转型方向与融资安排之间存在直接关联。")
    else:
        load.append("综合判断，公司报告期内未发生实质性的战略转型，资本开支与资本运作"
                    "均以维持现有业务为主。")
    return " ".join(load) + src_note(items[:3])


# ------------------------------------------------------------------ 7 历史融投资
def para_invest(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    rows = d.financing_rows()
    load = []
    # 数据侧：三年筹资活动现金流
    bor = get(r, "取得借款亿", "20251231")
    repay = get(r, "偿还债务亿", "20251231")
    fin = get(r, "筹资净额亿", "20251231")
    inv = get(r, "吸收投资亿", "20251231")
    bor23 = get(r, "取得借款亿", "20231231")
    repay23 = get(r, "偿还债务亿", "20231231")
    load.append(f"从现金流量表看，2025 年公司取得借款收到的现金 {yi(bor)} 亿元、"
                f"偿还债务支付的现金 {yi(repay)} 亿元、吸收权益性投资 {yi(inv)} 亿元，"
                f"筹资活动现金流净额 {yi(fin)} 亿元"
                f"（2023 年为取得借款 {yi(bor23)} 亿元、偿还债务 {yi(repay23)} 亿元）。")
    h1b, h1r = get(r, "取得借款亿", H1), get(r, "偿还债务亿", H1)
    h1fin = get(r, "筹资净额亿", H1)
    if np.isfinite(h1b) or np.isfinite(h1fin):
        load.append(f"{H1_FLOW}筹资活动现金流净额为 {yi(h1fin)} 亿元"
                    f"（取得借款 {yi(h1b)} 亿元、偿还债务 {yi(h1r)} 亿元，未年化），"
                    + ("仍处于净融入状态" if np.isfinite(h1fin) and h1fin > 0 else "已转为净流出，处于净还债状态")
                    + "。")
    if np.isfinite(get(r, "利息支付亿", "20251231")):
        load.append(f"2025 年分配股利、利润或偿付利息支付的现金合计 {yi(get(r, '利息支付亿', '20251231'))} 亿元。")
    # 事实侧：IPO、再融资、债券、重整投资
    if rows:
        kinds = "、".join(sorted({tesc(i.kind) for i in rows if i.kind})[:6])
        lead = R.choice([
            f"公司披露的股本与债务融资脉络包括：{kinds}。",
            f"公开信息中与公司直接相关的融资与资本运作包括：{kinds}。",
        ])
        load.append(lead)
        FIN_RE = re.compile(r"IPO|增发|定增|可转债|配股|债券|借款|贷款|授信|重整投资|战略投资|募资|募集")
        big = [i for i in rows if i.scale and re.search(r"亿|万元", str(i.scale))]
        # 已解除/终止的协议（如天邦食品 2026-09 被投资人单方解约的重整投资协议）
        # 不能与已完成的融资并列，否则读者会以为钱已到账
        DEAD_RE = re.compile(r"解除|终止|中止|撤回|未实施|被否|失败|未获")
        live = [i for i in big if not DEAD_RE.search(i.text)]
        if live:
            big = live
        if big:
            # 优先真正的融资类条目（IPO/增发/可转债/借款/重整投资），再按时间取最近的
            pick = sorted(big, key=lambda i: (0 if FIN_RE.search(f"{i.kind} {i.text}") else 1,
                                              -i.sort_key[0] * 10000 - i.sort_key[1]))[:2]
            load.append("其中规模较大的两笔为：" +
                        "；".join(f"{tesc(str(i.time))}{tesc(i.kind or '')}"
                                  f"（{tesc(cut(str(i.scale), 30))}）"
                                  + ("，\u8be5\u4e8b\u9879\u540e\u7eed\u5df2\u7ec8\u6b62\u6216\u89e3\u9664\uff0c\u4e0d\u6784\u6210\u5df2\u5230\u4f4d\u8d44\u91d1"
                                     if DEAD_RE.search(i.text) else "")
                                  for i in pick) + "\u3002")
    # 股本与分红
    sh, dv = r["share"], r["div"]
    seg = f"股本方面，近三年披露股本变动 {sh['n2023']} 次"
    if sh["reasons"]:
        seg += f"（{tesc(sh['reasons'])}）"
    if np.isfinite(sh.get("first_total", np.nan)) and np.isfinite(sh.get("last_total", np.nan)) and sh["first_total"] > 0:
        seg += (f"；总股本由 2021 年末的 {num_txt(sh['first_total'], 2)} 亿股变为 "
                f"{num_txt(sh['last_total'], 2)} 亿股（{signed_pct((sh['last_total'] / sh['first_total'] - 1) * 100, 2)}）")
    load.append(seg + "。")
    if dv["n"] > 0:
        load.append(f"分红方面，近三年现金分红 {dv['n']} 次、累计每股派现 {num_txt(dv['per_share'], 2)} 元"
                    f"（最近一次 {dv['last_date']}）——"
                    + ("在利润承压的阶段仍维持了分红" if ctx["arch"] in ("expansion", "steady")
                       else "分红规模与利润的下滑幅度相比仍然有限") + "。")
    else:
        load.append("分红方面，近三年未实施现金分红" +
                    ("，与重整期间的资金约束一致。" if ctx["arch"] == "reorg" else
                     "，在全部样本中属于分红能力偏弱的一端。"))
    # 再融资公告
    nref = r["events"]["ev"].get("再融资", 0)
    if nref:
        t = " ".join(r["events"]["titles"].get("再融资", []))
        kinds2 = [lab for pat, lab in [(r"向特定对象发行|非公开发行", "定向增发"),
                                       (r"可转换公司债券", "可转债"),
                                       (r"发行股份购买", "发行股份购买资产"),
                                       (r"募集说明书|募集资金", "募集资金使用")] if re.search(pat, t)]
        load.append(f"近三年“再融资”类公告 {nref} 条" +
                    (f"，涉及{'、'.join(kinds2)}" if kinds2 else "") + "。")
    return " ".join(x for x in load if x) + src_note(rows[:3] if rows else d.融资历史[:2])


# ------------------------------------------------------------------ 8 未来潜在融资需求
def para_need(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    debt = get(r, "负债率", H1)
    ni = get(r, "归母亿", H1)
    roe = get(r, "ROE", H1)
    cash = get(r, "货币资金亿", H1)
    st = get(r, "短期债务亿", H1)
    ibd = get(r, "有息负债亿", H1)
    ocf = get(r, "现金流亿", H1)
    csr = get(r, "现金短债比", H1)
    load = []
    tier = ctx["tier"]
    # 一、缺口量化
    if np.isfinite(st) and np.isfinite(cash):
        gap_lo = max(0.0, st - cash)
        loss_ann = 2 * abs(ni) if np.isfinite(ni) and ni < 0 else 0.0
        gap_hi = gap_lo + loss_ann
        seg = (f"{H1_END}货币资金 {yi(cash)} 亿元，而短期债务 {yi(st)} 亿元"
               f"（现金短债比 {num_txt(csr, 2)} 倍）")
        if np.isfinite(ocf):
            seg += f"，{H1_FLOW}经营现金流净额 {yi(ocf)} 亿元"
        seg += "。"
        if gap_lo > 0.5:
            seg += (f"按“短期债务减去账面货币资金”的滚动偿付口径，静态缺口约 {yi(gap_lo)} 亿元；"
                    f"若再计入上半年亏损的年化额（{yi(loss_ann)} 亿元），"
                    f"维持一年正常经营所需的外部资金约 {yi(gap_lo)}---{yi(gap_hi)} 亿元。")
        else:
            seg += "账面货币资金可以覆盖短期债务，缺口不体现在静态偿付层面。"
        load.append(seg)
    # 二、分层判断（与第 14 章的分层口径一致）
    if tier == 1:
        seg = (f"按第 \\ref{{sec:financing-need}} 节的三档划分，公司属于第一档“补血型”："
               f"2026 年上半年归母净利润 {yi(ni)} 亿元、6 月末资产负债率 {num_txt(debt, 1)}\\%。")
        if np.isfinite(debt) and debt > 80:
            seg += "负债率已超过 80\\%，净资产被亏损侵蚀的程度较深，属于全部样本中资产负债表最紧张的一组。"
        load.append(seg)
        paths = R.sample([
            "定向增发（需股价配合，且控股股东需放弃优先认购或同步增资）",
            "债务重组或展期（与银行和债券持有人协商）",
            "出售非核心资产与参股股权",
            "引入国资或产业投资人（部分公司以控制权让渡为对价）",
        ], 3)
        load.append("可行的融资路径按现实性排序为：" + "、".join(paths) + "。")
    elif tier == 2:
        load.append(f"按第 \\ref{{sec:financing-need}} 节的三档划分，公司属于第二档“保壳型”："
                    f"近三年重大重组与并购类公告 {r['events']['ev'].get('重大重组与并购', 0)} 条，"
                    f"2026 年上半年归母净利润 {yi(ni)} 亿元，"
                    f"融资需求更多体现为“资产置换 + 维持上市地位”，而不是扩产。")
    elif tier == 3:
        load.append(f"按第 \\ref{{sec:financing-need}} 节的三档划分，公司属于第三档“扩张型”："
                    f"2026 年上半年 ROE {num_txt(roe, 1)}\\%（未年化，折合约 {num_txt(roe * 2, 1)}\\%）、"
                    f"6 月末资产负债率 {num_txt(debt, 1)}\\%，资产负债表仍具备加杠杆空间；"
                    f"融资用途以产能扩张、品类并购与海外布局为主，"
                    f"单笔规模通常在 5---20 亿元量级，会被市场定价为成长而非补血。")
    else:
        if np.isfinite(ni) and ni < 0:
            load.append(f"公司 2026 年上半年归母净利润为负（{yi(ni)} 亿元），"
                        f"但 6 月末资产负债率 {num_txt(debt, 1)}\\% 尚未进入第一档"
                        f"（亏损且负债率 $>$65\\%）的区间，当前融资需求以补充流动资金、"
                        f"支撑低谷期经营性支出为主。")
        elif d.融资需求线索 or (np.isfinite(get(r, "在建工程亿", H1)) and get(r, "在建工程亿", H1) > 1):
            load.append(f"公司 2026 年 6 月末资产负债率 {num_txt(debt, 1)}\\%、"
                        f"2026 年上半年 ROE {num_txt(roe, 1)}\\%（未年化），"
                        f"资产负债表尚有余量，融资需求不是“补血型”的刚性需求，"
                        f"而是围绕并购整合、项目投入与营运资金的主动性需求。")
        else:
            load.append(f"公司 2026 年 6 月末资产负债率 {num_txt(debt, 1)}\\%、"
                        f"2026 年上半年 ROE {num_txt(roe, 1)}\\%（未年化），"
                        f"资产负债表稳健、盈利水平平淡，暂不存在刚性融资需求；"
                        f"潜在的融资需求以技改扩产、并购或被并购为主。")
    # 三、公司自身的融资线索（事实底稿）
    cues = d.融资需求线索
    if cues:
        recent = cues[-3:]
        load.append("公开披露的下一步融资线索包括：" +
                    "；".join((f"{tesc(str(i.time))} " if i.time else "") + tesc(cut(i.text, 60))
                              for i in recent) + "。")
    elif d.has("重整", "预重整"):
        load.append("截至目前公司仍处于预重整/重整程序中，重整投资人的招募与投资款到位"
                    "是未来一年最主要的外部资金来源。")
    # 四、投资支出（在建工程/在建投入）对资金的占用
    cip = get(r, "在建工程亿", H1)
    capex = get(r, "购建支出亿", H1)
    if np.isfinite(cip) and cip > 0.5 and np.isfinite(capex) and capex > 0:
        load.append(f"资金需求还要叠加在建工程：期末在建工程 {yi(cip)} 亿元、"
                    f"2026 年上半年购建固定资产等支出 {yi(capex)} 亿元（未年化），"
                    f"这部分支出在周期底部通常会被主动放缓。")
    return " ".join(load) + src_note(cues[:3])


# ------------------------------------------------------------------ 组装
def tex_company(r: dict, d, ctx: dict) -> str:
    name = tex_escape(r["名称"])
    L = [r"\subsubsection{%s（%s）}" % (name, r["代码"]),
         r"\label{co:%s}" % r["代码"], ""]
    L += [r"\pfl{公司基本情况} " + para_basic(r, d, ctx), ""]
    L += [r"\pfl{历史股价} " + para_price(r, d, ctx), ""]
    L += [CH.price_chart(r), ""]
    L += [r"\pfl{过去周期分析} " + para_cycle(r, d, ctx), ""]
    L += [r"\pfl{盈利情况} " + para_profit(r, d, ctx), ""]
    L += [CH.fin_table(r), ""]
    L += [CH.fin_chart(r), ""]
    L += [r"\pfl{财务分析} " + para_finance(r, d, ctx), ""]
    L += [r"\pfl{重大战略转型} " + para_strategy(r, d, ctx), ""]
    if len(d.financing_rows()) >= 3:
        L += [CH.financing_table(r, d.financing_rows()[:14]), ""]
    L += [r"\pfl{历史融投资情况} " + para_invest(r, d, ctx), ""]
    L += [r"\pfl{未来潜在融资需求分析} " + para_need(r, d, ctx), ""]
    # 本小节的资料来源（事实底稿里所有带来源的条目，去重后统一列出）
    srcs = [i.source for i in d.items if getattr(i, "source", "")]
    if srcs:
        L += [src_block(srcs), ""]
    L.append("")
    return "\n".join(L)
