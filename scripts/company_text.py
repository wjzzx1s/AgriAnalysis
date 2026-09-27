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
import company_digest as DG

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


def _fresh(ctx: dict, ph: str, overlap: int = 12) -> bool:
    """同一家公司内部避免重复叙述：与已用过的句子有 12 字以上重叠就判为旧料。"""
    used = ctx.setdefault("used", [])
    if not ph:
        return False
    for y in used:
        ni = len(ph) - overlap + 1
        if ni > 0 and any(ph[k:k + overlap] in y for k in range(ni)):
            return False
    used.append(ph)
    return True


def _strip_holder_clause(s: str) -> str:
    """定位段里若以子句形式写出“控股股东为…/实际控制人为…”，删掉（后面有结构化的股权结构句）。

    必须锚在子句开头：像“2019 年广西农村投资集团成为控股股东、2023 年 10 月更名”这种
    把“控股股东”当宾语的叙述是事件本身，不能删。
    """
    s = re.sub(r"(?:^|[；;，,。])\s*(?:公司)?(?:的)?(?:控股股东|实际控制人|第一大股东)"
               r"(?:为|是|：|[\u4e00-\u9fff]{2,12}(?:持股|持有))[^；;。]{0,40}(?=[；;。]|$)", "", s)
    s = re.sub(r"[、，,]\s*[^，。；、]{2,10}(?:为|是)(?=[；;。]|$)", "", s)   # 残留的“、中信集团为”
    s = re.sub(r"[、，,]\s*(?=[；;。]|$)", "", s)
    # 底稿定位段本身若收在半截话上（“…2026 年 1 月完成向。”），丢掉最后一段
    tail = s.rstrip(" 。；;")
    if re.search(r"[为与和在至从对将及等以到向]$", tail):
        segs = re.split(r"[，,；;]", tail)
        if len(segs) > 1:
            s = "，".join(segs[:-1]) + "。"
        else:                       # 整段只有一个子句且未写完：整句不要
            sents = [x for x in re.split(r"。", tail) if x.strip()]
            s = "。".join(sents[:-1]) + "。" if len(sents) > 1 else ""
    return s.replace("；。", "。").strip(" ；;，,")


def _dstr(x) -> str:
    """YYYY-MM-DD → “YYYY 年 M 月 D 日”（正文里不用连字符日期）。"""
    m = re.match(r"\s*((?:19|20)\d{2})[-/年]\s*(\d{1,2})[-/月]?\s*(\d{1,2})?", str(x or ""))
    if not m:
        return str(x or "—")
    y, mo, da = m.group(1), int(m.group(2)), m.group(3)
    return f"{y} 年 {mo} 月" + (f" {int(da)} 日" if da else "")


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
    """（已弃用，仅保留供查考）按字数硬切并补省略号。
    正文改用 company_digest.phrase()：在子句边界上选优、不产生省略号。
    历史问题：硬切会出现“1,850.0……”“支……”这类切在数字/词中间的片段。"""
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
    # 只认近年、且指向司法重整程序的表述；历史公告里出现过“退市风险警示”不等于现在在重整中
    recent = [i for i in list(d.风险与困境) + list(d.其他要点)
              if (getattr(i, "year", None) or 0) >= 2025 or not getattr(i, "year", None)]
    risk = " ".join(i.text for i in recent) + " " + (d.position or "")
    neg = r"不存在|未发生|未涉及|不涉及|否认|无[^，。；]{0,8}(?:重整|重组)"
    if re.search(r"预重整|破产重整|重整计划|法院受理[^。；]{0,12}重整|进入重整程序|被申请重整"
                 r"|重整投资人|裁定受理.{0,8}重整", risk):
        # 同一条里若是否认/自查说明（“均不存在……破产重整……”），不构成重整事实
        if not all(re.search(neg, x) for x in re.findall(r"[；;。][^；;。]*", risk)
                   if re.search(r"重整", x)):
            return "reorg"
    if "ST" in str(r.get("名称", "")) and re.search(r"退市风险警示|终止上市", risk):
        return "shell"
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


# 能把股价阶段“解释掉”的强事件：收购、转让、控制权、定增、重整、处罚等；
# “项目投入进度”“股东大会决议”这类事项与股价拐点没有对应关系，不用于对齐
STRONG_EVENT_RE = re.compile(
    r"收购|并购|重组|重整|预重整|转让|受让|剥离|注入|资产置换|控制权|易主|实际控制人变更|"
    r"定增|定向增发|非公开发行|可转债|配股|H 股上市|回购|股权激励|退市风险警示|撤销退市|"
    r"处罚|立案|问询函|违约|逾期|冻结|诉讼|仲裁|破产|减值")


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
_ENTITY_TAIL_RE = re.compile(r"(公司|集团|局|委员会|委员会|委|会|院|大学|厂|社|中心|银行|农场|"
                             r"自然人|家族|个人|人民政府|国有资产监督管理委员会|国资委|"
                             r"管理委员会|管委会|控股|投资|基金|协会|研究所)$")


def _entity(x: str) -> str:
    """股权结构取出的名字必须像“主体”，否则宁可不写。

    拒绝“、实际控制人、时任董事长…收到证监会《立案告知书》”“与佳沃集团有限公司签署”
    这类从公告串里切出来的残句。
    """
    x = (x or "").strip(" 、，。；：")
    m = re.search(r"(?:变更为|改由|由)([^，。；：、《》（）]{2,24})$", x)
    if m:
        x = m.group(1)
    x = re.split(r"为(?:其|公司)|全资子公司|控股子公司|下属子公司|大股东", x)[0].strip(" 、，。；：")
    if not x or len(x) > 24:
        return ""
    if re.search(r"收到|立案|告知书|处罚|问询|公告|披露|签署|转让|变更|辞职|减持|冻结|、", x):
        return ""
    if not _ENTITY_TAIL_RE.search(x):
        return ""
    return x


def para_basic(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    name = tesc(r["名称"])
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
        _pos = _strip_holder_clause(d.position)
        load.append(f"{opener}{tesc(_pos)}{'' if _pos.endswith(('。', '）')) else '。'}")
    elif r.get("主营"):
        load.append(f"{opener}主营业务为“{tesc(DG.tidy(r['主营']))}”，"
                    f"按申万行业分类（2021 版）归属三级行业“{ind3}”。")
    else:
        load.append(f"{opener}按申万行业分类（2021 版）归属三级行业“{ind3}”。")

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
        seg.append(f"截至 {_dstr(r.get('行情日期'))}收盘价 {num_txt(r.get('最新收盘'), 2)} 元，"
                   f"流通市值 {num_txt(cap, 1)} 亿元，近一年{signed_pct(r.get('近一年涨跌%'))}")
        if rank and total:
            seg.append(f"流通市值在三级行业“{ind3}”的 {total} 家公司中按由大到小排{order_cn(rank)}")
    yoy = r.get("近一年涨跌%", np.nan)
    if np.isfinite(yoy) and np.isfinite(ctx["med"].get("yoy", np.nan)):
        m = ctx["med"]["yoy"]
        seg.append(f"近一年涨跌幅{'高于' if yoy > m else '低于'}全样本中位数"
                   f"（{signed_pct(m)}）{num_txt(abs(yoy - m), 1)} 个百分点")
    if seg:
        load.append("，".join(seg) + "。")

    # 主营构成（当期半年报 vs 2021 年年报）
    c = r.get("comp") or {}
    if c.get("ok"):
        _pairs = [(k, v) for k, v in c["新"] if np.isfinite(v) and v > 0.05]
        items = "；".join(f"{tesc(k)} {num_txt(v, 1)}\\%" for k, v in _pairs)
        _n_items = len(_pairs)
        if items:
            unit = "行业" if "行业" in str(c.get("类别")) else "产品"
            # 分部收入含内部交易、未抵消至合并口径时可能超过 100%，
            # 写成“收入占比 131.1%”会显得荒谬，须改成“分部数据”并说明不可比
            _mx = max([v for _, v in c["新"] if np.isfinite(v)] or [0])
            _ord = {1: "仅一项", 2: "前两位", 3: "前三位"}.get(_n_items, "前三位")
            if _mx > 100:
                load.append(f"按 {ctx['comp_period']}披露的{unit}分部数据（含内部交易、未抵消至合并口径）"
                            f"为{items}；该口径与合并营业收入不可直接比较。")
            elif _n_items <= 1:
                load.append(f"按 {ctx['comp_period']}披露的{unit}构成，收入几乎全部来自{items}。")
            else:
                load.append(f"按 {ctx['comp_period']}披露的{unit}构成，收入占比{_ord}为{items}。")
            if c.get("旧") and c.get("首位变化") and _mx <= 100:
                load.append(f"与 2021 年年报相比，第一大{unit}口径由“{tesc(c['旧'][0][0])}”"
                            f"（{num_txt(c['旧'][0][1], 1)}\\%）变为“{tesc(c['新'][0][0])}”"
                            f"（{num_txt(c['新'][0][1], 1)}\\%）；两期披露的分类口径有调整，"
                            f"占比差异中同时包含分类因素。")

    # 沿革里程碑：只保留股权与主业层面的变化，用提炼后的短句归纳成一句
    MILE_RE = re.compile(r"重组|控制权|易主|实际控制人|更名|简称|转型|吸收合并|整体上市|"
                         r"借壳|重大资产|注入|收购|剥离|划转|改制")
    milestones = []
    pos_years = set(re.findall(r"(19|20)\d{2}", d.position or ""))
    for i in hist[1:]:
        if not i.text or not MILE_RE.search(i.text):
            continue
        # 定位段里已经讲过的年份不再重复叙述（否则沿革与定位会互相抄一遍）
        if i.year and str(i.year) in pos_years and len(hist) > 4:
            continue
        # 上市与发行细节已在前文交代，里程碑只留股权与主业的变化
        if re.search(r"首发|首次公开发行|IPO|挂牌上市|发行价|网上发行|上市公告书", i.text) \
                and not re.search(r"重组|控制权|更名|转型|吸收合并|注入|剥离|划转", i.text):
            continue
        ph = DG.phrase(i, budget=40)
        if ph and ph not in _dedup_phrases(milestones + [ph]):
            milestones.append(ph)
        if len(milestones) >= 3:
            break
    if milestones:
        lead = R.choice([
            "沿革上的关键变化是：",
            "股权与主业沿革上，",
            "从沿革看，",
        ])
        load.append(f"{lead}{'；'.join(tesc(x) for x in milestones)}。")

    # 股权结构：控股股东与实际控制人（画像的必写项，取自底稿的“其他要点”与沿革）
    holder = ctrl = ""
    held_pct = ""
    for i in list(d.其他要点) + hist:
        t = DG.tidy(i.text)
        if not re.search(r"控股股东|实际控制人|第一大股东", t):
            continue
        if not holder:
            m = re.search(r"(?:控股股东|第一大股东)(?:为|是|：)?\s*([^，。；：、《》（）]{2,26})", t)
            if m:
                holder = _entity(m.group(1))
        if not ctrl:
            m = re.search(r"实际控制人(?:为|是|：)?\s*([^，。；：、《》（）]{2,22})", t)
            if m:
                ctrl = _entity(m.group(1))
        if not held_pct:
            m = re.search(r"持股\s*([\d.]+)\s*%|持股比例\s*(?:为|约)?\s*([\d.]+)\s*%", t)
            if m:
                held_pct = (m.group(1) or m.group(2))
        if holder and (ctrl or held_pct):
            break
    bits = []
    if holder:
        bits.append(f"控股股东为{holder}" + (f"（持股 {held_pct}%）" if held_pct else ""))
    if ctrl and ctrl not in holder:
        bits.append(f"实际控制人为{ctrl}")
    if bits:
        load.append("股权结构方面，" + "；".join(tesc(x) for x in bits) + "。")
    return " ".join(load) + src_note(hist[:3])
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
                    f"波动率由高到低排{order_cn(ctx['rank_vol'])}")
        load.append(seg + "。")
    # 把最大的两段涨跌与公司事件对齐（事件一律用提炼后的短句，不照抄公告）
    legs = r.get("legs")
    anchors = []
    if legs is not None and len(legs):
        for _, leg in legs.sort_values("幅度", key=lambda s: s.abs(), ascending=False).head(2).iterrows():
            ev = [x for x in events_in(d, leg["起"].year, leg["止"].year,
                                       t0_month=int(pd.Timestamp(leg["起"]).month),
                                       t1_month=int(pd.Timestamp(leg["止"]).month))
                  if STRONG_EVENT_RE.search(x.text)]
            if ev:
                anchors.append((leg, ev[-1]))
    parts = []
    seen_ev: set[int] = set()
    for l, e in anchors[:2]:
        if id(e) in seen_ev:
            continue
        seen_ev.add(id(e))
        ph = DG.phrase(e, budget=38)
        if not ph:
            continue
        # “2026 年 6 月，公司……”→“（2026 年 6 月）公司……”，接在“同期”之后不断读
        ph = re.sub(r"^((?:19|20)\d{2} 年(?: \d{1,2} 月)?(?:---\d{4} 年)?)[，,]\s*",
                    lambda m: f"（{m.group(1)}）", ph)
        parts.append(f"{ym(l['起'])} 至 {ym(l['止'])}股价{'上涨' if l['幅度'] > 0 else '下跌'}"
                     f"{signed_pct(l['幅度'])}，同期{tesc(ph)}")
    if parts:
        load.append("把股价阶段与公司事件对齐看，" + "；".join(parts) + "。")
        load.append(R.choice([
            "整体上看，区间的几处大级别拐点都能在公司的资本运作、股权变动或风险事件上找到对应，"
            "股价波动有明显的公司层面驱动，而非单纯的行业 beta。",
            "把这些阶段与公司事件对齐后可以看到，几轮大涨大跌多由公司自身的资本运作与风险事件触发，"
            "行业景气只解释了其中一部分。",
            "从时间对应关系看，公司层面的资本运作与股权、风险事件解释了区间内多数急涨急跌，"
            "与行业指数的同步性相对有限。",
        ]))
    elif np.isfinite(r.get("rho_ind", np.nan)):
        load.append(f"区间内股价与申万农林牧渔指数的月度收益相关系数为 {r['rho_ind']:+.2f}，"
                    f"走势更多由板块整体与农产品价格驱动，公司个体事件对股价的解释力有限。")
    cites = [e for _, e in anchors]
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
    # 归纳句：把形态与波动水平收束成一句判断
    if up is not None and dn is not None:
        mv = ctx["med"].get("vol", np.nan)
        if np.isfinite(r.get("年化波动", np.nan)) and np.isfinite(mv):
            tone = "波动明显大于样本中位数" if r["年化波动"] > mv * 1.15 else (
                "波动小于样本中位数" if r["年化波动"] < mv * 0.9 else "波动与样本中位数接近")
            _amp = max(abs(up["幅度"]), abs(dn["幅度"]))
            load.append(f"综合区间形态看，该股单段涨跌幅度"
                        f"{'偏大、以趋势段为主' if _amp > 45 else '相对温和、以震荡为主'}"
                        f"（最大主升 {signed_pct(up['幅度'])}、最大主跌 {signed_pct(dn['幅度'])}），"
                        f"年化波动率 {num_txt(r['年化波动'], 1)}\\% 与全样本中位数 {num_txt(mv, 1)}\\% 相比{tone}。")
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
    med_ind = ctx.get("med_ind_roe", float("nan"))
    if np.isfinite(roe) and np.isfinite(med_roe):
        gap = roe - med_roe
        choices = []
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
    # 业绩变动的成因与公司举措：分成两句写，不再把公告长句直接搬进正文
    rev_txt, ni_txt = (f"{e:.2f}" if np.isfinite(e) else None,
                       f"{abs(f):.2f}" if np.isfinite(f) else None)
    causes, actions = [], []
    for i in d.items:
        if i.section not in ("风险与困境", "战略与转型", "主营与结构"):
            continue
        # 只写报告期附近的事实：2013、2014 年的旧公告不能解释 2026 年的业绩
        _y = getattr(i, "year", None)
        if _y and _y < 2024:
            continue
        t = DG.tidy(i.text)
        if not re.search(r"价格|成本|汇率|税率|需求|销量|供给|产能|疫情|天气|减值|计提|毛利|利息|"
                         r"费用|亏损|下滑|下降|减少|超出预期|过剩|跌幅|涨幅", t):
            continue
        # 问询函、招股书风险提示、净资产/利润等报表数字都不是成因
        if re.search(r"问询函|监管函|风险提示|招股说明书|招股书|净资产|可供分配|未分配利润|"
                     r"持股|质押|冻结", t):
            continue
        if rev_txt and rev_txt in t and ni_txt and ni_txt in t:
            continue      # 只是复述当期数字，不构成成因
        # 年报口径的“实现营业收入 … 归属于上市公司股东的净利润 …”属数据复述，
        # 与画像中的财务表重复；只有提到原因/减值/价格等驱动时才保留
        if (re.search(r"实现营业收入|全年营业收入", t)
                and re.search(r"归属于上市公司股东的净利润|净利润", t)
                and not re.search(r"原因|由于|受|导致|拖累|影响|减值|计提|停产|疫情|火灾|重整", t)):
            continue
        ph = DG.phrase(i, budget=42)
        if not ph:
            continue
        if re.search(r"(原因|由于|受.{0,10}影响|导致|拖累|主因|系|因.{0,8}(?:价格|成本|汇率|税率|疫情|"
                     r"减值|需求|销量|供给|天气))", t) \
                and not re.search(r"针对|为应对|已采取|将采取|拟通过", t):
            causes.append(ph)
        elif (re.search(r"(拟|计划|将|已|正在|推进|压减|优化|降本|治理|落地|拓展|布局|盘活|聚焦|"
                        r"提升|加强|开展|实施|加快|推动|建设|投产|扩产|设立|收购|剥离|出售|"
                        r"改造|技改|控本|增效|调整|退出|瘦身|完善|落实|加大|减少|淘汰|合作|"
                        r"转型|自建|推广|试点|降低|压缩|严控|统筹)", t[:56])
              # 缺主语/无动词的报表片段、诉讼计提、比率、公告程序语都不能算“应对举措”
              and not re.search(r"问询函|处罚|立案|警示|扣非亏损|未分配利润|可供分配|利润分配预案|"
                                r"报表层面|净资产为负|退市风险|亏损额|监事|会议|审议|议案|"
                                r"诉讼|计提|预计负债|仲裁|罚款|风险提示|招股书|质押|冻结", t)
              and re.match(r"^(?:公司|本公司|集团|子公司|下属|控股|管理层|董事会|拟|计划|将|已|正在|"
                           r"推进|开展|实施|加快|推动|加大|压缩|严控|调整|优化|聚焦|剥离|出售|收购|"
                           r"自建|合作|推广|试点|淘汰|退出|减少|降低|提升|加强|完善|落实)",
                           re.sub(r"^\s*(?:19|20)\d{2}\s*年(?:\s*\d{1,2}\s*月)?\s*[，,]?\s*", "", t))):
            actions.append(ph)
    causes = [x for x in _dedup_phrases(causes) if _fresh(ctx, x)]
    actions = [x for x in _dedup_phrases(actions) if _fresh(ctx, x)]
    if causes:
        load.append("从公司披露的原因看，业绩变动主要来自：" +
                    "；".join(tesc(x) for x in causes[:2]) + "。")
    if actions:
        load.append(R.choice([
            "针对上述压力，公司披露的应对举措包括：",
            "公司披露的应对举措集中在：",
            "面对这一局面，公司披露的举措包括：",
            "公司给出的应对方向是：",
        ]) + "；".join(tesc(x) for x in actions[:2]) + "。")
    # 归纳：按当期盈利方向给出判断（只用数据侧事实，不对未来下断言）
    if np.isfinite(f):
        if f < 0:
            dir_txt = "仍处亏损区间"
            if np.isfinite(fp) and fp < 0:
                dir_txt += ("、亏损同比收窄" if abs(f) < abs(fp) else "、亏损同比扩大")
            elif np.isfinite(fp) and fp > 0:
                dir_txt += "、由盈转亏"
            rank_txt = f"，半年 ROE 在三级行业内按由高到低排{order_cn(rank_roe)}" if rank_roe else ""
            load.append(f"综合看，公司{dir_txt}{rank_txt}，单位盈利能力的修复依赖行业景气与"
                        f"自身成本端的改善，报表弹性主要体现为价格与销量的方向性变化。")
        else:
            cmp_txt = ""
            if np.isfinite(med_roe):
                cmp_txt = (f"（{'高于' if roe > med_roe else '低于'}全样本半年 ROE 中位数 "
                           f"{num_txt(med_roe, 2)}\\%）" if np.isfinite(roe) else "")
            load.append(f"综合看，公司在报告期维持盈利{cmp_txt}，"
                        f"利润的可持续性取决于{tesc(r.get('三级') or '本行业')}景气的延续与成本管控的执行。")
    return " ".join(x for x in load if x) + src_note(causes + actions)
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
        if abs(ch) < 0.05:
            s += f"，与 {y}基本持平"
        else:
            s += f"，较 {y}{'上升' if ch > 0 else '下降'} {num_txt(abs(ch), 1)} 个百分点"
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
    net = np.nan
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
                    + (R.choice(["短期偿付压力较大", "短期偿债指标偏紧"]) if r["流动比率"] < 1
                       else R.choice(["短期指标尚可", "短期偿债能力处于正常区间",
                                      "短期流动性无明显缺口"])) +
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
    # 归纳：债务结构判断（只用资产负债表与现金流数据）
    judge = []
    if np.isfinite(csr) and np.isfinite(net):
        if csr < 0.5 and net > 0:
            judge.append(f"账面货币资金对有息负债与短期债务的覆盖不足，滚动偿付对新增融资的依赖度较高")
        elif csr >= 1:
            judge.append(f"现金短债比 {num_txt(csr, 2)} 倍，短期偿付压力可控")
        else:
            judge.append(f"现金短债比 {num_txt(csr, 2)} 倍，短期资金安排偏紧")
    if np.isfinite(dbt) and np.isfinite(med_debt):
        judge.append(f"资产负债率{'高于' if dbt > med_debt else '低于'}样本中位数 {num_txt(abs(dbt - med_debt), 1)} 个百分点")
    if np.isfinite(ibd) and np.isfinite(lt) and ibd > 0:
        judge.append(f"有息负债中{'长期' if lt > ibd / 2 else '短期'}债务占比更高，期限结构"
                     f"{'对短债滚动的压力较小' if lt > ibd / 2 else '仍以滚动续作为主'}")
    if judge:
        load.append("综合看，" + "；".join(judge) + "。")
    # 事实中的财务风险（审计意见、净资产为负、诉讼冻结等）：先归类，再给一两条要点
    SEV = [r"净资产为负|资不抵债|退市风险", r"重整|破产", r"违约|逾期|冻结|失信",
           r"立案|处罚|问询函", r"诉讼|仲裁", r"质押|减持"]
    risks = [i for i in d.风险与困境 if re.search("|".join(SEV), i.text)
             # “本报告期无重大诉讼”不是风险；早年公告不构成当前风险
             and not re.search(r"无重大诉讼|无诉讼|不存在|未发生|无违规|未受到|无重大违法", i.text)
             and ((getattr(i, "year", None) or 2026) >= 2024)]

    def sev(i):
        for k, pat in enumerate(SEV):
            if re.search(pat, i.text):
                return k
        return len(SEV)

    risks = sorted(risks, key=lambda i: (sev(i), -i.sort_key[0]))[:2]
    if risks:
        kinds = []
        for i in risks:
            k = DG.risk_kind(i)
            if k not in kinds:
                kinds.append(k)
        ph = [x for x in _dedup_phrases([x for x in (DG.phrase(i, budget=36) for i in risks) if x])
              if _fresh(ctx, x)]
        if ph:
            if len(kinds) >= 2 and len(ph) >= 2:
                head = "公司披露的风险集中在" + "、".join(tesc(k) for k in kinds[:2]) + "两类："
                body = "；".join(f"{'一是' if k == 0 else '二是'}{tesc(x)}" for k, x in enumerate(ph))
            else:
                head = f"公司披露的{tesc(kinds[0]) if kinds else '主要'}风险为："
                body = "；".join(tesc(x) for x in ph)
            load.append(head + body + "。")
    return " ".join(x for x in load if x) + src_note(risks)
# ------------------------------------------------------------------ 6 重大战略转型
def para_strategy(r: dict, d, ctx: dict) -> str:
    R = ctx["rng"]
    ev = r["events"]["ev"]
    items = [i for i in d.战略与转型 if not DG.is_strategy_noise(i)]
    load = []
    # 按主题归类（同一条事实可能落在两个主题，取第一个命中），组内按时间取最近的若干条
    groups: dict[str, list] = {}
    for i in items:
        th = DG.themes_of(i)
        key = th[0] if th else "其他动作"
        groups.setdefault(key, []).append(i)
    top = sorted(groups.items(), key=lambda kv: (-len(kv[1]), max(x.sort_key for x in kv[1])))
    parts = []
    seen_ph: list[str] = []           # 跨主题组去重：同一项目第二次改用“上述项目”回指
    for name, xs in top[:2]:
        ph = []
        for x in sorted(xs, key=lambda i: i.sort_key, reverse=True):
            p = DG.phrase(x, budget=34)
            if not p or p in ph or not _fresh(ctx, p):
                continue
            for y in seen_ph:
                hit = ""
                for k in range(max(len(p) - 10 + 1, 0)):
                    if p[k:k + 10] in y:
                        hit = p[k:k + 10]
                        break
                if hit:
                    p = p.replace(hit, "上述项目")
                    break
            if p and p not in seen_ph:
                ph.append(p)
                seen_ph.append(p)
            if len(ph) >= 2:
                break
        if ph:
            parts.append(f"{tesc(name)}（{len(xs)} 项）：" + "；".join(tesc(p) for p in ph))
    if parts:
        lead = R.choice([
            "近三年公司的战略动作集中在：",
            "从公开披露看，公司的战略推进集中在：",
            "公司的战略动作可归为以下几类：",
        ])
        load.append(lead + "；".join(parts) + "。")
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
    # 结论句：按证据强度分级（避免“零并购却写外延扩张”这类与正文相反的判断）
    n_ma = ev.get("重大重组与并购", 0)
    n_tr = ev.get("对外投资与转型", 0)
    if ctx["arch"] == "reorg":
        load.append("综合判断，公司当前的战略重心不是扩张而是化解债务与完成重整，"
                    "业务层面的调整让位于司法重整程序。")
    elif n_ma >= 1 or n_tr >= 1:
        load.append(f"综合判断，报告期内公司有 {n_ma + n_tr} 条与战略相关的公告落地"
                    f"（重大重组与并购 {n_ma} 条、对外投资与转型 {n_tr} 条），"
                    f"资本运作与主业调整之间存在直接关联。")
    elif c.get("首位变化") or abs(c.get("首位占比变化", 0) or 0) >= 10:
        load.append("综合判断，公司报告期内的变化主要发生在收入结构层面，"
                    "属于口径与业务重心的再平衡，而非外延式扩张。")
    elif "ST" in str(r["名称"]):
        load.append("公司证券简称带风险警示标识，报告期内的资本运作以维持上市地位为主线，"
                    "属于第 \\ref{sec:financing-strategy} 节界定的“跨界与保壳”路径。")
    else:
        load.append("综合判断，报告期内公司未披露实质性的重组、并购或转型安排，"
                    "资本开支以维持现有产能与业务为主。")
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
    # 现金流量表口径：缺失科目不写（正文中“— 亿元”没有意义）
    _parts = []
    if np.isfinite(bor):
        _parts.append(f"取得借款收到的现金 {yi(bor)} 亿元")
    if np.isfinite(repay):
        _parts.append(f"偿还债务支付的现金 {yi(repay)} 亿元")
    if np.isfinite(inv):
        _parts.append(f"吸收权益性投资 {yi(inv)} 亿元")
    _base = ("从现金流量表看，2025 年公司" + "、".join(_parts)) if _parts else "从现金流量表看，2025 年公司"
    _y23 = []
    if np.isfinite(bor23):
        _y23.append(f"取得借款 {yi(bor23)} 亿元")
    if np.isfinite(repay23):
        _y23.append(f"偿还债务 {yi(repay23)} 亿元")
    load.append(f"{_base}，筹资活动现金流净额 {yi(fin)} 亿元"
                + (f"（2023 年为{'、'.join(_y23)}）。" if _y23 else "。"))
    h1b, h1r = get(r, "取得借款亿", H1), get(r, "偿还债务亿", H1)
    h1fin = get(r, "筹资净额亿", H1)
    if np.isfinite(h1b) or np.isfinite(h1fin):
        load.append(f"{H1_FLOW}筹资活动现金流净额为 {yi(h1fin)} 亿元"
                    f"（取得借款 {yi(h1b)} 亿元、偿还债务 {yi(h1r)} 亿元，未年化），"
                    + ("仍处于净融入状态" if np.isfinite(h1fin) and h1fin > 0 else "已转为净流出，处于净还债状态")
                    + "。")
    if np.isfinite(get(r, "利息支付亿", "20251231")):
        load.append(f"2025 年分配股利、利润或偿付利息支付的现金合计 {yi(get(r, '利息支付亿', '20251231'))} 亿元。")
    # 事实侧：IPO、再融资、债券、重整投资（归纳为“以哪几类工具为主”，再给两笔规模最大的）
    if rows:
        KIND_TOOL_RE = re.compile(r"IPO|首次公开|增发|配股|可转债|可转换|公司债|债券|中票|票据|短融|"
                                  r"借款|贷款|授信|融资租赁|优先股|重整投资|战略投资|资产注入|发行股份|"
                                  r"发行股份购买|股权融资|债务融资")
        kinds = []
        for i in rows:
            k = _kind_short(DG.tidy(i.kind))
            if not k or not KIND_TOOL_RE.search(k) \
                    or re.search(r"议案|额度|担保|说明|豁免|利息", k):
                continue
            if k not in kinds:
                kinds.append(k)
        if kinds:
            kinds_cn = "、".join(tesc(k) for k in kinds[:4]) + ("等" if len(kinds) > 4 else "")
            load.append(f"公开披露的融资记录共 {len(rows)} 笔，工具类型以{kinds_cn}为主；"
                        f"金额与用途见下表。")
        else:
            load.append(f"公开披露的融资记录共 {len(rows)} 笔，以股权与债务类融资为主；"
                        f"金额与用途见下表。")
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
            ph = []
            for i in pick:
                dt = DG.time_cn(i.time)
                kind = _kind_short(DG.tidy(i.kind))
                sc = DG.shorten(DG.money(DG.tidy(str(i.scale))), 46) if i.scale else ""
                sc = sc.replace("；", "，")
                p = f"{dt}，{kind}" if dt and kind else (f"{dt}，{sc}" if dt else kind)
                if sc and kind:
                    p = f"{dt}，{kind}，{sc}" if dt else f"{kind}，{sc}"
                if not p:
                    p = DG.phrase(i, budget=52)
                if p:
                    ph.append(p.strip("，"))
            if ph:
                load.append("其中规模最大的两笔为：" +
                            "；".join(f"{tesc(x)}" + ("（该事项后续已终止或解除，不构成已到位资金）"
                                                   if DEAD_RE.search(x) else "")
                                      for x in ph) + "。")
    # 股本与分红
    sh, dv = r["share"], r["div"]
    seg = f"股本方面，近三年披露股本变动 {sh['n2023']} 次"
    if sh["reasons"]:
        seg += f"（{tesc(sh['reasons'])}）"
    if np.isfinite(sh.get("first_total", np.nan)) and np.isfinite(sh.get("last_total", np.nan)) and sh["first_total"] > 0:
        _ch = (sh["last_total"] / sh["first_total"] - 1) * 100
        if abs(_ch) < 0.005:
            seg += f"；总股本自 2021 年末以来未发生变化（{num_txt(sh['last_total'], 2)} 亿股）"
        else:
            seg += (f"；总股本由 2021 年末的 {num_txt(sh['first_total'], 2)} 亿股变为 "
                    f"{num_txt(sh['last_total'], 2)} 亿股（{signed_pct(_ch, 2)}）")
    load.append(seg + "。")
    if dv["n"] > 0:
        _d = str(dv.get("last_date") or "")
        _note = "，最近一次实施在 " + ym(_d) if re.match(r"\d{4}", _d) else ""
        load.append(f"分红方面，近三年现金分红 {dv['n']} 次、合计每股派现 "
                    f"{num_txt(dv['per_share'], 2)} 元{_note}。")
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
    # 归纳：融资结构判断（只用现金流与融资记录形态）
    if np.isfinite(fin):
        tone = ("以债务滚动为主、股权融资为补充" if (not rows or np.isfinite(inv) and inv <
                (abs(fin) if np.isfinite(fin) else 1)) else "股权与债务融资并举")
        load.append(f"综合看，公司融资结构上{tone}；2025 年筹资活动现金流净额 "
                    f"{yi(fin)} 亿元，{'融资节奏仍以维持存量债务周转为主' if fin <= 0 else '年度内仍为净融入'}，"
                    f"与前述经营与投资现金流的方向基本一致。")
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
    gap_lo = gap_hi = np.nan
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
            seg += f"按“短期债务减去账面货币资金”的滚动偿付口径，静态缺口约 {yi(gap_lo)} 亿元"
            if loss_ann > 0.05:
                seg += (f"；若再计入上半年亏损的年化额（{yi(loss_ann)} 亿元），"
                        f"维持一年正常经营所需的外部资金约 {yi(gap_lo)}---{yi(gap_hi)} 亿元。")
            else:
                seg += "；上半年盈利或接近盈亏平衡，该缺口不随经营亏损进一步扩大。"
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
        elif (np.isfinite(debt) and debt >= 65) or (np.isfinite(csr) and csr < 1)\
                or (np.isfinite(ni) and ni < 0):
            # 高杠杆/短债覆盖不足/亏损：写“补血型”，不再套用扩张话术
            _why = ("资产负债率偏高（" + num_txt(debt, 1) + "\\%）"
                    if np.isfinite(debt) and debt >= 65
                    else ("现金短债比 " + num_txt(csr, 2) + " 倍、短债覆盖不足"
                          if np.isfinite(csr) and csr < 1 else "上半年尚未扭亏"))
            load.append(f"公司 2026 年 6 月末资产负债率 {num_txt(debt, 1)}\\%、"
                        f"2026 年上半年 ROE {num_txt(roe, 1)}\\%（未年化），{_why}，"
                        f"融资需求首先用于置换与滚动存量债务、补充营运资金，"
                        f"属于“补血型”而非扩张型。")
        elif np.isfinite(get(r, "在建工程亿", H1)) and get(r, "在建工程亿", H1) > 1:
            load.append(f"公司 2026 年 6 月末资产负债率 {num_txt(debt, 1)}\\%、"
                        f"2026 年上半年 ROE {num_txt(roe, 1)}\\%（未年化），"
                        f"资产负债表尚有余量，融资需求不是“补血型”的刚性需求，"
                        f"而是配套在建项目投入的主动性安排。")
        else:
            _sw = R.choice([
                "资产负债表稳健、盈利水平平淡，暂不存在刚性融资需求；"
                "潜在的融资需求以技改扩产、并购或被并购为主。",
                "账面杠杆不高、盈利能力一般，短期内没有必须依靠外部融资才能维持的经营缺口；"
                "后续融资更可能指向技改、扩产或产业并购。",
                "财务结构相对宽松而盈利弹性有限，融资属于可选项而非必选项，"
                "触发条件多与产能建设或外延并购相关。",
                "资产端与负债端都没有明显压力，融资需求以相机抉择的扩张型用途为主。",
            ])
            load.append(f"公司 2026 年 6 月末资产负债率 {num_txt(debt, 1)}\\%、"
                        f"2026 年上半年 ROE {num_txt(roe, 1)}\\%（未年化），" + _sw)
    # 三、公司自身的融资线索（归类后写，不再逐条搬运公告）
    cues = d.融资需求线索
    buckets: dict[str, list] = {"股权融资线索": [], "债务与授信安排": [], "资本开支安排": []}
    for i in cues[-4:]:
        t = DG.tidy(i.text)
        if re.search(r"未披露|尚未披露|未新增|无新增|不涉及|不存在|未发生新的|无相关安排|无进展|未见|"
                     r"问询函|关注函|监管函|纪律处分", t):
            continue                        # “未披露新的股权融资”不是线索，只是没有信息
        ph = DG.phrase(i, budget=40)
        if not ph:
            continue
        if re.search(r"定增|非公开|向特定对象|可转债|配股|发行股份|增发|H 股|股权融资|募集说明书|受理|注册|上市地位", t):
            buckets["股权融资线索"].append(ph)
        elif (re.search(r"授信|借款|贷款|债券|中票|短融|融资额度|担保|融资余额|租赁|续发|额度", t)
              and not re.search(r"实现亏损|亏损|净利润|净资产|营业收入", t)):
            buckets["债务与授信安排"].append(ph)
        elif re.search(r"在建|项目|投产|建设|资本开支|投入|购建|扩产|储备库", t):
            buckets["资本开支安排"].append(ph)
    # 同一类里高度重复的线索只写一次（例如同一笔抵押贷款被两条公告重复记录）
    buckets = {k: _dedup_phrases(v) for k, v in buckets.items()}
    segs = [f"{k}：{'；'.join(tesc(x) for x in v[:2])}" for k, v in buckets.items() if v]
    if segs:
        load.append("公开披露的后续资金安排线索包括：" + "；".join(segs) + "。")
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
    # 归纳：需求性质与量级
    if np.isfinite(gap_lo):
        if gap_lo > 0.5:
            _tail = ("融资的时点与规模更多取决于债权人与重整投资人的进度" if ctx["arch"] == "reorg"
                     else R.choice(["融资的时点与规模更多取决于信用条件与资本市场窗口",
                                    "能否落地取决于授信续作与发行窗口的配合",
                                    "融资节奏将受制于银行续贷意愿与股权融资窗口"]))
            _need = ("债务接续为主" if ctx["tier"] == 1
                     else R.choice(["补充流动性与项目投入为主", "营运资金周转与在建项目投入为主",
                                    "补充营运资金为主、项目投入为辅"]))
            load.append(f"综合看，公司的外部资金需求以{_need}，"
                        f"滚动偿付口径下的静态缺口约 {yi(gap_lo)} 亿元，{_tail}。")
        else:
            load.append(R.choice([
                "综合看，公司在静态偿付层面不存在缺口，外部融资更多是配合扩张节奏与并购整合的主动性安排，"
                "而非偿债压力驱动。",
                "静态偿付不存在缺口，后续融资更可能服务于产能或并购安排，而不是填补流动性窟窿。",
                "以现有货币资金与经营现金流衡量，公司不存在刚性补血的紧迫性，融资动作更多是主动型的。",
            ]))
    return " ".join(load) + src_note(cues[:3])
# ------------------------------------------------------------------ 组装
def _kind_short(k: str) -> str:
    """融资工具名的报告式简称（“公开发行可转换公司债券”→“可转债”），便于同类归并。"""
    k = re.sub(r"（[^）]*）|\([^)]*\)", "", k).strip()
    for pat, lab in ((r"IPO|首次公开发行|首次公开", "IPO"),
                     (r"可转换公司债|可转债", "可转债"),
                     (r"向特定对象发行|非公开发行|定向增发|增发", "定向增发"),
                     (r"发行股份购买", "发行股份购买资产"),
                     (r"公司债", "公司债"), (r"中期票据|中票", "中期票据"),
                     (r"超短期融资券|超短融", "超短融"), (r"短期融资券|短融", "短融"),
                     (r"配股", "配股"), (r"优先股", "优先股"),
                     (r"银行借款|借款|贷款", "银行借款"), (r"授信", "银行授信"),
                     (r"融资租赁", "融资租赁"), (r"重整投资", "重整投资"),
                     (r"战略投资", "战略投资")):
        if re.search(pat, k):
            return lab
    return k[:10]


def _dedup_phrases(items: list[str], overlap: int = 8) -> list[str]:
    """同一段里明显重复的短语只保留一次；若只是复述同一对象，则改用回指。"""
    out: list[str] = []
    for x in items:
        hit = ""
        for y in out:
            ni = len(x) - overlap + 1
            for k in range(max(ni, 0)):
                if x[k:k + overlap] in y:
                    hit = x[k:k + overlap]
                    break
            if hit:
                break
        if not hit:
            out.append(x)
            continue
        if len(hit) >= 10:                      # 同一项目名，第二次用“上述项目”回指
            y2 = x.replace(hit, "上述项目")
            if y2 not in out and len(y2) > 8:
                out.append(y2)
    return out


def _para(text: str) -> str:
    """段落级排版收口：重复句读清理 + 中文与数字之间补空格（拼接时可能漏掉）。"""
    text = re.sub(r"。{2,}", "。", text)
    text = re.sub(r"，{2,}", "，", text)
    text = re.sub(r"[，、；]\s*。", "。", text)
    return DG.space_out(text)


def tex_company(r: dict, d, ctx: dict) -> str:
    name = tex_escape(r["名称"])
    L = [r"\subsubsection{%s（%s）}" % (name, r["代码"]),
         r"\label{co:%s}" % r["代码"], ""]
    L += [r"\pfl{公司基本情况} " + _para(para_basic(r, d, ctx)), ""]
    L += [r"\pfl{历史股价} " + _para(para_price(r, d, ctx)), ""]
    L += [CH.price_chart(r), ""]
    L += [r"\pfl{过去周期分析} " + _para(para_cycle(r, d, ctx)), ""]
    L += [r"\pfl{盈利情况} " + _para(para_profit(r, d, ctx)), ""]
    L += [CH.fin_table(r), ""]
    L += [CH.fin_chart(r), ""]
    L += [r"\pfl{财务分析} " + _para(para_finance(r, d, ctx)), ""]
    L += [r"\pfl{重大战略转型} " + _para(para_strategy(r, d, ctx)), ""]
    if len(d.financing_rows()) >= 3:
        L += [CH.financing_table(r, d.financing_rows()[:14]), ""]
    L += [r"\pfl{历史融投资情况} " + _para(para_invest(r, d, ctx)), ""]
    L += [r"\pfl{未来潜在融资需求分析} " + _para(para_need(r, d, ctx)), ""]
    # 本小节的资料来源（事实底稿里所有带来源的条目，去重后统一列出）
    srcs = [i.source for i in d.items if getattr(i, "source", "")]
    if srcs:
        L += [src_block(srcs), ""]
    L.append("")
    return "\n".join(L)
