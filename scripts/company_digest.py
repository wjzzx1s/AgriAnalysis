#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""事实底稿的“提炼层”：把公告原文式的长句改写成研究报告语气的短句。

底稿 data/facts/*.yaml 的条目多是从公告与定期报告里摘录的原文，直接搬进正文有三个问题：
  1) **照抄公告**：夹带文号、经办机构、股份明细等程序性内容，读者抓不到重点；
  2) **省略号**：早期的 cut() 按字数硬切，出现“786,000,000 股新股……”“降到……”这类半截句；
  3) **口径不一**：日期写成“12 月 27 日”而年份另附括号，金额写成“470,814.00 万元”，
     同一段里“元 / 万元 / 亿元”三种量级混排。

本模块只做**取舍与换算**，不新增底稿里没有的数字：

  tidy(s)        版式归一：中英文与数字间空格、去掉“未查得”等检索痕迹与省略号
  money(s)       量纲归一：元/万元 → 亿元，股 → 万股/亿股（两位小数）
  time_cn(t)     时间归一：2026-06-30 / 2026年6月29日 → “2026 年 6 月”
  lead_date(s)   摘出条目前置日期并剔除（日期由正文统一放在句首，不再写在括号里）
  digest(it)     子句打分选优 → 一句完整、无省略号的提炼句（可作正文的论据短语）
  phrase(it)     提炼句 + 日期前缀 → 可整句写进正文的短语

写作约束：
  * 输出永远以词/子句边界收尾，**不产生“……”**；
  * 保留关键量（金额、比例、产能、份额）与动作（收购、转让、定增、投产……），
    丢弃括注里的明细（文号、股东名册、经办机构）；
  * 程序性表述（“经证监会核准”“董事会审议通过”）默认剔除，除非它本身就是事件；
  * 数字中的千分位逗号不参与断句，避免“1,155,754,328.18 元”被切成“155 元”。
"""
from __future__ import annotations

import re

CJK = "\u4e00-\u9fff"
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_COMMA_HOLD = "\x00"          # 数字内千分位逗号的临时占位符

# 动作词：出现即说明该子句是“事件”，优先保留
ACTION_RE = re.compile(
    r"收购|并购|重组|重整|转让|受让|出让|过户|划转|转让|出售|剥离|置出|置入|注入|增资|扩股|引入|认购|发行|上市|挂牌|"
    r"定增|非公开|配股|可转债|可转换|债券|中票|超短融|短融|借款|贷款|授信|担保|质押|"
    r"回购|激励|持股计划|分红|派现|设立|成立|新建|投产|达产|扩产|产能|募资|募集|"
    r"违约|逾期|冻结|查封|诉讼|仲裁|处罚|立案|问询|警示|退市|破产|计提|减值|"
    r"签署|协议|合同|中标|解除|终止|撤回|变更|控制权|易主|更名|托管|"
    r"亏损|扭亏|业绩预告|销量|出栏|存栏|价格|成本|毛利|补贴|补助|退税|召回|疫情|火灾")

# 标志性事件：权重最高的一类
MARQUEE_RE = re.compile(
    r"IPO|首发|上市|挂牌|借壳|重组上市|重大资产重组|控制权|易主|实际控制人变更|"
    r"重整|预重整|破产|退市风险警示|撤销退市|定增|定向增发|非公开发行|向特定对象发行|"
    r"可转债|公司债|H 股|配股|并购|收购|资产注入|资产置换|剥离|出售|股权激励|员工持股")

# 程序性/复述性子句：出现即降权（这些内容进正文只会读起来像公告搬运）
PROCEDURAL_RE = re.compile(
    r"号文|证监许可|核准批复|核准文件|工商登记|营业执照|登记托管|证券登记|董事会决议|"
    r"监事会|股东大会审议通过|议案|公告编号|详见|以下简称|备查|招股说明书|募集说明书|"
    r"归属于上市公司股东的净利润|实现营业收入|营业收入为|保荐机构|主承销商|承销方式|"
    r"上市推荐人|发行方式|发行市盈率|网下|网上定价")

# 财务复述：与画像中的财务表重复，不作为正文论据
RESTATE_RE = re.compile(r"净利润|营业收入|净资产|总资产|资产负债率|每股收益|毛利率|"
                        r"加权平均净资产收益率|利润总额|现金流")

# 成因/趋势类子句：没有动作词时仍值得保留（“主因价格下跌”“产能过剩”）
REASON_RE = re.compile(r"主因|原因|由于|受.{0,8}影响|导致|下滑|上升|增长|减少|过剩|加剧|"
                       r"萎缩|承压|转亏|扭亏|改善|恶化|提升|下降|回暖|疲弱")

# 以这些词开头的子句多为残句（合并后仍可能出现）
FRAGMENT_HEAD_RE = re.compile(r"^(且|并|及|等|其中|即|而|故|以便|同时|分别|均|亦|就|致)")
# 列举式（“向下列银行申请……”“要点：A、B、C”）在正文里应改写成概括句，不进摘录
LISTY_RE = re.compile(r"下列|如下|：|:|（?一\)?）|①|②|；\s*[（(]?\d[）)]")
# 价格/数量补充语（“转让价格 6.83 亿元”“发行价 5.99 元/股”）：离开标的就没有信息量，不能单独入选
PRICE_ONLY_RE = re.compile(r"^(转让价格|交易价格|交易金额|成交金额|作价|价款|发行价格|发行价|发行市盈率|"
                           r"价格|金额|数量|比例|第\s*\d+\s*[-—\d]*\s*(层|栋|号|期)|注册资本|债券代码|"
                           r"股票代码|证券代码)")
# 有信息量的名词（标的/主体/产能），用于判断子句是否“有内容”
SUBSTANTIVE_RE = re.compile(r"股权|股份|资产|公司|子公司|集团|基地|项目|工厂|产线|生产线|产能|销量|"
                            r"出栏|存栏|价格|成本|毛利|市场|份额|产品|业务|债务|借款|借款|授信|债券|"
                            r"基金|平台|牧场|胶园|土地|矿|品牌|渠道|研发|许可|批复|协议|合同")

PAREN_KEEP_RE = re.compile(r"亿元|万元|亿股|万股|%|吨|万头|含税|未年化|不含税|同比|人民币|"
                           r"经审计|扣非|原口径|更正后|追溯|预重整|重整|一期|二期")
PAREN_DROP_RE = re.compile(r"号文|证监许可|工商|登记|编号|详见|以下简称|备查|名册|"
                           r"章程|议事规则|评估报告|审计报告|中介机构|保荐|承销|①|②|"
                           r"搜狐证券|数据来源|来源|新浪|同花顺|东方财富|雪球|万得|wind|Wind")

_TRAIL_PUNCT = "，,、；;：:。 ."


# ------------------------------------------------------------------ 版式归一
def space_out(s: str) -> str:
    """中文与半角数字/字母之间加一个空格（本报告的正文排版约定）。"""
    s = re.sub(rf"([{CJK}])\s*([0-9A-Za-z])", r"\1 \2", s)
    s = re.sub(rf"([0-9A-Za-z%])\s*([{CJK}])", r"\1 \2", s)
    s = re.sub(r"[ ]{2,}", " ", s)
    return s


def tidy(s) -> str:
    """底稿文本 → 版式规范的纯文本（不改事实，只清噪声）。"""
    s = str(s or "")
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"[…]+", "", s)                       # 绝不保留省略号
    s = re.sub(r"[（(]\s*[）)]", "", s)               # 空括号
    # “公司披露/公告称”这类公告动词（研究报告直接陈述事实）
    s = re.sub(r"(公司|本公司|其)(?:于\s*(?:19|20)\d{2}\s*年[^，。；]{0,10})?\s*披露", r"\1", s)
    s = re.sub(r"(?:^|[，,；;。])\s*(?:公告|年报|半年报|定期报告)?(?:显示|披露|载明)[，,]?", "", s)
    s = re.sub(r"(?:^|[，,；;。])\s*(?:公告|公司|其)称[，,]?", "", s)
    s = re.sub(r"(?:^|[，,；;])\s*公告(?:拟|将|计划|披露)?\s*(?=[\u4e00-\u9fff])", "", s)
    # 承销/保荐等中介程序语（“招商证券主承销”“上市推荐人平安证券”等对判断无信息量）
    s = re.sub(r"[，,；;]?\s*(?:由)?[\u4e00-\u9fff]{2,12}(?:证券|投行|银行|信托|基金)"
               r"[^，。；]{0,14}?(?:联席主承销商?|主承销商?|保荐机构|保荐人|上市推荐人|承销方式|承销商)", "", s)
    s = re.sub(r"[，,；;]?\s*(?:联席主承销商?|主承销商|保荐机构|保荐人|上市推荐人|承销方式|余额包销|包销)"
               r"[^，。；]{0,12}", "", s)
    s = re.sub(r"[，,；;]\s*(?=[，,；;])", "", s)        # 去掉因删除产生的空子句
    # 公文标题去壳：《关于终止…的公告》→ 终止…，标题里的信息保留、公文腔去掉
    s = re.sub(r"《(?:关于|就)?\s*([^》]{2,44}?)\s*(?:的公告|的议案|的批复|的通知|的回函|的函|"
               r"的说明|的提示性公告|的进展公告|的专项报告)?》", r"\1", s)
    s = re.sub(r"^\s*[（(]?(?:一|二|三|四|五|六|七|八|九|十|\d+)[）)、.]\s*", "", s)
    # 检索痕迹（“未查得”“本次检索未查得”等）连同其括注一起去掉
    s = re.sub(r"[（(][^（()）]{0,44}(?:未查得|未查到|暂未查得|未披露该|无公开披露)[^（()）]{0,44}[）)]", "", s)
    s = re.sub(r"[，,；;]?\s*本次检索[^。；]{0,44}(?:未查得|未查到)[^。；]{0,44}", "", s)
    s = re.sub(r"[，,；;]?\s*(?:未查得|未查到|暂未查得|无公开披露)[^，。；]{0,30}", "", s)
    # 文号与核准类程序性片段（“证监许可[2015]2862 号文核准”“中国证监会 2015 年 12 月 9 日核准”等）
    s = re.sub(r"(?:经)?(?:中国)?(?:证监会|证监许可|证监发字|上交所|深交所|交易所|国家发改委|发改委|"
               r"商务部|国务院国资委)[^，。；]{0,28}?\[?[\d]{{2,4}}[\]）)]?[^，。；]{{0,12}}?\s*号?\s*文?\s*"
               r"(?:核准|批复|批准|同意|备案)?[，,]?", "", s)
    s = re.sub(r"[^，。；]{0,20}证监许可[^，。；]{0,30}[，,]?", "", s)
    s = re.sub(r"(?:^|[，,；;])\s*(?:经|由|已|获|于|被|该[^，。；]{0,6})?[^，。；]{0,10}"
               r"(?:审核通过|核准批复|批复核准)(?:的|后)?[，,]?", "", s)
    s = re.sub(r"\[[\d]{{4}}[\]\d]{{0,10}}\]", "", s)
    s = re.sub(r"（[\d]{{4}}）[\d]{{1,5}} ?号", "", s)
    s = re.sub(r"(?<=\d)，(?=\d{3}(?!\d))", ",", s)      # 数字内的全角逗号归一
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[，,、；;：:]+", "", s)
    return space_out(s).strip(_TRAIL_PUNCT).strip()


# ------------------------------------------------------------------ 量纲换算
def _fmt(v: float, nd: int = 2) -> str:
    return f"{v:,.{nd}f}"


def money(s: str) -> str:
    """金额与股数量纲归一：统一到亿元/万元、亿股/万股（保留两位小数）。"""
    s = str(s or "")

    def _amount(m):
        raw, unit = m.group(1), m.group(2)
        num = float(raw.replace(",", ""))
        pre = s[max(0, m.start() - 8):m.start()]
        # 单价、每股派现、每吨价格等“每单位金额”保留“元”量级
        if re.search(r"每股|/股|/吨|/公斤|/头|/羽|元/|派|面值|红利|权益|行权|发行价|每股收益", pre):
            return f"{_fmt(num, 2)} {unit}" if num < 1e4 else m.group(0)
        if unit == "元":
            if num >= 1e8:
                return f"{_fmt(num / 1e8)} 亿元"
            if num >= 1e4:
                return f"{_fmt(num / 1e4)} 万元"
            return f"{_fmt(num, 0)} 元"
        if unit in ("万元", "万港元", "万美元"):
            if num >= 1e4:
                return f"{_fmt(num / 1e4)} 亿{unit[1:]}"
            return f"{_fmt(num)} {unit}"
        if unit in ("亿元", "亿港元", "亿美元"):
            return f"{_fmt(num)} {unit}"
        return m.group(0)

    s = re.sub(rf"({_NUM})\s*(亿元|万元|万港元|万美元|元)(?![股市/])", _amount, s)
    s = re.sub(rf"({_NUM})\s*(亿港元|亿美元)", lambda m: f"{_fmt(float(m.group(1).replace(',', '')))} {m.group(2)}", s)
    s = re.sub(rf"({_NUM})\s*(港元|美元)(?![股/])", lambda m: f"{_fmt(float(m.group(1).replace(',', '')))} {m.group(2)}", s)

    def _share(m):
        num = float(m.group(1).replace(",", ""))
        if num >= 1e8:
            return f"{_fmt(num / 1e8)} 亿股"
        if num >= 1e4:
            return f"{_fmt(num / 1e4)} 万股"
        return f"{_fmt(num, 0)} 股"

    s = re.sub(rf"(?<![万亿])({_NUM})\s*股(?![份东权利本价票募集])", _share, s)
    return s


def pct(s: str) -> str:
    """百分号统一为半角且贴近数字（“35 %”→“35%”）。"""
    s = re.sub(r"(\d)\s*[%％]\s*(?=[^\s])", r"\1%", str(s))
    s = re.sub(r"(\d)\s*[%％]", r"\1%", s)
    return s


# ------------------------------------------------------------------ 时间归一
def time_cn(t) -> str:
    """时间字段 → “2026 年 6 月”“2019---2024 年”“2026 年”。"""
    t = str(t or "").strip()
    if not t:
        return ""
    m = re.match(r"^((?:19|20)\d{2})\s*[-—~/]\s*((?:19|20)\d{2})\s*$", t)
    if m:
        return f"{m.group(1)}---{m.group(2)} 年"
    m = re.match(r"^((?:19|20)\d{2})\s*[-—~./年]\s*(\d{1,2})\s*(?:[-—~./月]\s*(\d{1,2}))?", t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y} 年 {mo} 月" if 1 <= mo <= 12 else f"{y} 年"
    m = re.match(r"^((?:19|20)\d{2})", t)
    return f"{m.group(1)} 年" if m else ""


_LEAD_DATE_RE = re.compile(
    r"^\s*(?P<y>(?:19|20)\d{2})\s*年\s*(?P<mo>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日\s*[，,、:：]?\s*"
    r"|^\s*(?P<y2>(?:19|20)\d{2})\s*[年]?\s*(?P<mo2>\d{1,2})\s*月\s*[，,、:：]?\s*"
    r"|^\s*(?P<y3>(?:19|20)\d{2})\s*[-/.]\s*(?P<mo3>\d{1,2})\s*(?:[-/.]\s*(?P<d3>\d{1,2}))?\s*[，,、:：]?\s*"
    r"|^\s*(?P<mo4>\d{1,2})\s*月\s*(?P<d4>\d{1,2})\s*日\s*[，,、:：]?\s*"
    r"|^\s*(?P<y5>(?:19|20)\d{2})\s*[-—~]\s*(?P<y6>(?:19|20)\d{2})\s*年?\s*[，,、:：]?\s*"
    r"|^\s*(?P<y7>(?:19|20)\d{2})\s*年\s*[，,、:：]?\s*"
    r"|^\s*(?P<y8>(?:19|20)\d{2})\s*[，,、:：]\s*")
_YEAR_TAIL_RE = re.compile(
    r"^(上半年末|下半年末|年度报告|半年度报告|季度报告|年度末|年度|上半年|下半年|半年报|"
    r"年报|季报|报告|全年|年内|年中|一季度|二季度|三季度|四季度|第一季度|度|末|初|报|内|中)")


def _absorb_tail(s: str) -> tuple[str, str]:
    """把“年度/年末/上半年末/年度报告”等时间后缀并入日期串，避免“2025 年，末总股本…”。

    “起”也一并吸入（“2026 年 6 月 29 日起撤销……”→ 日期串写“2026 年 6 月起”）。
    """
    suffix = ""
    while True:
        m = _YEAR_TAIL_RE.match(s)
        if not m or m.group(1) in ("内", "中") and not suffix:
            break
        suffix += m.group(1)
        s = s[m.end():]
        if m.group(1) in ("度", "末", "初", "报", "内", "中"):
            continue                       # 这些单字后面可能还有“末/度”
        break
    if s.startswith("起"):
        suffix += "起"
        s = s[1:]
    return suffix, s


def lead_date(s: str) -> tuple[str, str, bool]:
    """摘出条目前置日期。

    返回（规范化日期，去日期后的正文，日期是否含年份）：
      “2026年6月29日召开…”   → ("2026 年 6 月", "召开…", True)
      “6 月公司前身…成立”      → ("6 月", "公司前身…成立", False)
      “2021—2023 年连续亏损”   → ("2021---2023 年", "连续亏损", True)
      “2025年度公司计提…”      → ("2025 年度", "公司计提…", True)
    """
    s = str(s or "")
    m = _LEAD_DATE_RE.match(s)
    if not m:
        return "", s, False
    gd = m.groupdict()
    tail = s[m.end():]
    has_year = bool(gd.get("y") or gd.get("y2") or gd.get("y3") or gd.get("y5")
                    or gd.get("y7") or gd.get("y8"))
    suffix = ""
    if has_year:
        suffix, tail = _absorb_tail(tail)
    if gd.get("y"):
        return f"{gd['y']} 年 {int(gd['mo'])} 月{suffix}", tail, True
    if gd.get("y2"):
        return f"{gd['y2']} 年 {int(gd['mo2'])} 月{suffix}", tail, True
    if gd.get("y3"):
        mo = int(gd["mo3"])
        return (f"{gd['y3']} 年 {mo} 月{suffix}" if 1 <= mo <= 12 else f"{gd['y3']} 年{suffix}"), tail, True
    if gd.get("mo4"):
        return f"{int(gd['mo4'])} 月 {int(gd['d4'])} 日", tail, False
    if gd.get("y5"):
        return f"{gd['y5']}---{gd['y6']} 年{suffix}", tail, True
    if gd.get("y7"):
        return f"{gd['y7']} 年{suffix}", tail, True
    if gd.get("y8"):
        return f"{gd['y8']} 年", tail, True
    return "", s, False


# ------------------------------------------------------------------ 括注精简
def prune_parens(s: str, limit: int = 20, keep_hint: bool = True) -> str:
    """删除过长或属明细/程序性的括注；保留含金额、比例、口径说明的短注。

    只处理成对的括注：落单的左括号说明原文在此被截断，其后的残句一并丢弃
    （否则会出现“1.68 亿元重整后遗留部分子公司借款逾期事项”这类粘连句）。
    """
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch in "（(":
            close = "）" if ch == "（" else ")"
            j = s.find(close, i + 1)
            if j < 0:                       # 落单左括号 → 丢弃其后残句
                break
            body = s[i + 1:j]
            dig = len(re.findall(r"\d", body))
            if PAREN_DROP_RE.search(body):
                drop = True
            elif keep_hint and PAREN_KEEP_RE.search(body) and len(body) <= limit + 6:
                drop = False
            else:
                drop = len(body) > limit or dig >= 4
            if drop:
                # 括注删除后左右会粘连（“……2,819 元（母公司口径）因……起诉……”），补一个顿点
                if (out and i > 0 and j + 1 < n
                        and not str(out[-1]).endswith(("，", "、", "。", "；", "："))
                        and s[j + 1] not in "，、。；）)]】"):
                    out.append("，")
                i = j + 1
                continue
            out.append(ch + body + close)
            i = j + 1
            continue
        if ch in "）)":                     # 落单右括号
            i += 1
            continue
        out.append(ch)
        i += 1
    return re.sub(r"[ ]{2,}", " ", "".join(out)).strip(_TRAIL_PUNCT)


# ------------------------------------------------------------------ 子句挑选
_MAIN_SPLIT = re.compile(r"[。；;！!]")
# 子句切分：只在逗号处断句；顿号是列举内部的连接，切开会产生“新增牛”这类半截短语
_SUB_SPLIT = re.compile(r"[，]|,(?!\d)")

# 以这些词开头说明它不是独立子句，必须与前一子句合并（“自 1992 年起使用”→拆成“起使用”就废了）
_MERGE_HEAD_RE = re.compile(r"^(起|的|且|并|及|等|其中|即|而|故|以便|同时|均|亦|就|于|在|为|与|和|或|"
                            r"使|令|致|用|由|自|以|向|对|将|含|包括|涵盖|分别|按期|如期)")
# 纯数量子句（“2,783.64 万元”“111.09 万元”）没有信息量，不能单独入选
_BARE_AMOUNT_RE = re.compile(rf"^[（(]?(?:约|不超过|不低于|合计|共计)?\s*{_NUM}\s*"
                             rf"(?:亿元|万元|万美元|亿港元|万港元|元|亿股|万股|股|吨|万头|%)?[）)]?$")


def _protect(s: str) -> str:
    """把数字里的千分位逗号换成占位符，避免断句把数字切开。"""
    return re.sub(r"(?<=\d),(?=\d{3}(?!\d))", _COMMA_HOLD, s)


def _restore(s: str) -> str:
    return s.replace(_COMMA_HOLD, ",")


def _clauses(s: str) -> list[tuple[int, str, str]]:
    """切子句；返回（原始位置序号，子句，所属主句）。位置用于最后按原文顺序拼接。"""
    s = _protect(s)
    out: list[tuple[int, str, str]] = []
    pos = 0
    for main in _MAIN_SPLIT.split(s):
        main = main.strip(" ，、：: ")
        if not main:
            continue
        subs = [x.strip(" ：:") for x in _SUB_SPLIT.split(main) if x.strip(" ：:")]
        if not subs:
            continue
        merged: list[str] = []
        for x in subs:                      # 残句并回前一个子句
            if merged and (_MERGE_HEAD_RE.match(x) or _BARE_AMOUNT_RE.match(x)
                           or len(x) <= 3):
                merged[-1] = merged[-1] + "，" + x
            else:
                merged.append(x)
        if len(merged) >= 2:                # 主语 + 首个谓语也算一个候选
            out.append((pos, _restore(merged[0]), main))
            pos += 1
        start = 1 if len(merged) >= 2 else 0
        for k in range(start, len(merged)):
            out.append((pos, _restore(merged[k]), main))
            pos += 1
    return out


def _has_amount(c: str) -> bool:
    return bool(re.search(rf"({_NUM})\s*(?:亿元|万元|亿港元|万美元|亿股|万股|吨|万头|%|元|股)", c))


def _score(c: str, idx: int, n: int, main: str = "") -> float:
    s = 0.0
    if _BARE_AMOUNT_RE.match(c):
        return -9.0
    if MARQUEE_RE.search(c):
        s += 3.4
    elif ACTION_RE.search(c):
        s += 2.6
    if re.search(rf"({_NUM})\s*(?:亿元|万元|亿港元|万美元|亿股|万股|吨|万头)", c):
        s += 2.0
    if re.search(r"\d+(?:\.\d+)?%", c):
        s += 1.0
    if re.search(r"产能|产量|销量|出栏|存栏|市占|份额|毛利率|净利率|产能利用率", c):
        s += 1.0
    if re.search(r"同比|较上年|增幅|降幅", c):
        s += 0.5
    if REASON_RE.search(c):
        s += 1.2
    if PROCEDURAL_RE.search(c):
        s -= 2.6
    if PRICE_ONLY_RE.search(c):
        s -= 2.6
    if not ACTION_RE.search(c) and not REASON_RE.search(c) \
            and not re.search(rf"({_NUM})\s*(?:亿元|万元|亿港元|万美元|亿股|万股|吨|万头|%)", c):
        s -= 4.0                       # 纯名词短语（“第 10-22 层办公写字楼”）不进正文
    if not SUBSTANTIVE_RE.search(c):
        s -= 0.8
    # 列举残段（主句里顿号成串时，后半个名字单独成句就是残段，如“云南海胶提供…担保”）
    if main.count("、") >= 3 and idx > 0 and not re.match(r"^(公司|本公司|控股股东|实际控制人|子公司|下属|发行|上市|本次)", c):
        s -= 2.0
    if re.match(r"^(公司|本公司|控股股东|实际控制人|子公司|下属子公司)", c):
        s += 0.6
    if FRAGMENT_HEAD_RE.search(c):
        s -= 1.6
    if LISTY_RE.search(c):
        s -= 1.4
    if RESTATE_RE.search(c) and not MARQUEE_RE.search(c):
        s -= 1.2
    if re.search(r"^\s*(?:1 月|2 月|3 月|4 月|5 月|6 月|7 月|8 月|9 月|10 月|11 月|12 月)", c):
        s -= 0.8
    if not ACTION_RE.search(c) and not re.search(r"\d", c):
        s -= 2.2
    ln = len(c)
    if ln > 52:
        s -= 1.3
    elif ln > 40:
        s -= 0.6
    elif ln < 8:
        s -= 1.4
    if idx == 0:
        s += 1.6                          # 首个子句通常是事件本身
    else:
        s += max(0.0, 0.9 - 0.14 * idx)
    return s


LEAD_VERB_RE = re.compile(
    r"^(将|以|向|对|拟|完成|通过|发行|收购|并购|转让|出售|设立|投资|增资|借款|获得|取得|"
    r"签署|披露|回购|变更|引入|剥离|募集|募资|实现|投产|新建|确定|申请|终止|解除|计提|"
    r"推进|开始|启动|置出|置入|注入|控股|参股|认购|担保|质押|减持|增持|分红|派发|亏损|"
    r"主导|联合|挂牌|上市|注入|更名|整合|瘦身|聚焦|推动|加快|收购|撤销|恢复|剥离|计提)")
SUBJECT_RE = re.compile(r"^(公司|本公司|该|其|集团|控股股东|实际控制人|股东|董事|全资|下属|"
                        r"子公司|控股子公司|标的|交易|发行|上市|本次|报告期|截至|经|由|作为)")


def shorten(s: str, limit: int) -> str:
    """把过长的子句压到 limit 以内：在逗号边界上截断，不制造半截词、不加省略号。

    若保留下来的部分不含数量、而原文别处含金额/比例，则优先把含数量的那一节留下
    （数量是正文最需要用到的信息）；列举串则取“等”之后的收束语。
    """
    s = str(s or "").strip(_TRAIL_PUNCT)
    if len(s) <= limit:
        return s
    segs = [x for x in re.split(r"[，,]", s) if x.strip()]   # 只按逗号收缩，顿号列举整体保留
    out: list[str] = []
    for seg in segs:
        cand = "，".join(out + [seg])
        if out and len(cand) > limit:
            if not any(_has_amount(x) for x in out) and _has_amount(seg) and len(cand) <= limit + 18:
                out.append(seg)
            break
        out.append(seg)
    r = "，".join(out).strip(_TRAIL_PUNCT)
    if not _has_amount(r) and any(_has_amount(x) for x in segs):
        amt = next((x for x in segs if _has_amount(x)), "")
        tail = _list_tail(amt)
        if tail and len(tail) >= 8:
            r = "，".join(out[:1] + [tail]) if out else tail
    return r or s[:limit].strip(_TRAIL_PUNCT)


def _list_tail(seg: str) -> str:
    """从列举串里取出收束语（“A、B、C 等工具对外融资不超过 20 亿元”→“对外融资不超过 20 亿元”）。"""
    m = re.search(r"等(?:方式|工具|形式|途径|手段|渠道|措施)?", seg)
    if m:
        return seg[m.end():].strip("，、 ")
    if "、" in seg:
        return seg.rsplit("、", 1)[-1].strip("，、 ")
    return seg


def digest(it, budget: int = 46) -> str:
    """一条事实 → 一句提炼后的短句（无省略号；不含前置日期，日期由调用方拼）。"""
    text = tidy(getattr(it, "text", it))
    text = money(pct(text))
    if not text:
        return ""
    _, body, _ = lead_date(text)
    if body:
        text = body
    text = prune_parens(text)
    if len(text) < 6:
        return ""
    # 整条都是程序性事项（保荐代表人、登记托管、决议序号……）时不写进正文
    if PROCEDURAL_RE.search(text) and not MARQUEE_RE.search(text) and len(text) < 40:
        return ""
    cands = _clauses(text)
    if not cands:
        return ""
    scored = [(_score(c, idx, len(cands), main), idx, c) for idx, c, main in cands]
    scored.sort(key=lambda t: (-t[0], t[1]))
    best_s, best_i, best = scored[0]
    if best_s < 0.2:                      # 没有任何事件/数字信息量，宁可不出句
        return ""
    keep: list[tuple[int, str]] = [(best_i, best)]
    for s2, i2, c2 in scored[1:]:
        if len(best) + len(c2) + 1 > budget:
            continue
        if s2 < max(1.0, 0.5 * best_s):
            continue
        if FRAGMENT_HEAD_RE.search(c2):
            continue
        if c2 in best or best in c2:
            continue
        if c2[:3] == best[:3]:           # “同比增长…，同比增长…”式的重复
            continue
        if re.match(r"^(同比|环比|较上年|同比增|同比减)", c2) and re.search(r"同比|环比|较上年", best):
            continue
        add_money = _has_amount(c2) and not _has_amount(best)
        if add_money or (len(keep) == 1 and s2 >= 0.8 * best_s):
            keep.append((i2, c2))
            break
    # 若选中的子句以“后/之后/时/以来/起”收尾，说明话没说完：把下一子句补上
    if re.search(r"(后|之后|时|以来|期间|此前)$", best.strip(_TRAIL_PUNCT)):
        for s2, i2, c2 in scored[1:]:
            if i2 <= best_i or s2 < 0.45 * best_s:
                continue
            if len(best) + len(c2) + 1 > budget + 14:
                continue
            keep.append((i2, c2))
            break
    keep.sort(key=lambda t: t[0])          # 按原文顺序拼接，避免语序倒错
    out = "，".join(c for _, c in keep)
    out = shorten(out, budget + 16)
    out = prune_parens(out, limit=14)
    out = re.sub(r"[，、]{2,}", "，", out).strip(_TRAIL_PUNCT)
    # 同一句里重复出现的子句（“以自有资产抵押向银行申请贷款，以自有资产抵押向银行申请贷款”）
    _segs: list[str] = []
    _seen: set[str] = set()
    for seg in re.split(r"[，,]", out):
        k = re.sub(r"^\s*(?:19|20)\d{2}\s*年(?:\s*\d{1,2}\s*月)?[，,]?\s*", "", seg)
        k = re.sub(r"^(?:公司|本公司|其|该)", "", k).strip()
        if len(k) >= 8 and k in _seen:
            continue
        _seen.add(k)
        _segs.append(seg)
    out = "，".join(_segs)
    # “募集资金使用情况：……”这类小标题式前缀去掉，直接写内容
    out = re.sub(r"^[^：:]{0,16}(?:情况|要点|安排|方案|措施|结构|明细)[：:]\s*", "", out)
    for lo, hi in (("“", "”"), ("《", "》")):
        if out.count(lo) != out.count(hi):   # 引号/书名号被截断时成对去掉，避免半对符号
            out = out.replace(lo, "").replace(hi, "").strip(_TRAIL_PUNCT)
    if re.match(r"^(预计|金额|规模|价格|数量|比例|其中|仅|共计|合计|约)", out):
        for s2, i2, c2 in sorted(scored, key=lambda x: -x[0]):
            if i2 >= (keep[0][0] if keep else 10**9):
                continue
            if 4 <= len(c2) <= 22 and not re.search(r"^[，,、]", c2):
                out = c2 + "，" + out
                break
    # 仍然收在连接词上（“商票逾期事件发酵后”）就去掉该连接词，避免半截话
    out = re.sub(r"(?:的)?(?:基础上|前提下|情况下|情形下|之后|以来|此前)$", "", out)
    if re.search(r"[^，。；]{3}(?:后|时)$", out) and len(out) >= 8:
        out = re.sub(r"(后|时)$", "", out)
    out = re.sub(r"^(公司)(?:公司|本公司|集团)", r"\1", out)     # “公司公司股票…”式重复主语
    if re.match(r"^(开市|收市|停牌|复牌|涨跌幅)", out):
        out = "公司股票" + out
    elif not SUBJECT_RE.match(out) and LEAD_VERB_RE.match(out):
        out = "公司" + out
    return space_out(out).strip(_TRAIL_PUNCT)


def phrase(it, budget: int = 46) -> str:
    """事实条目 → “2026 年 6 月，公司……”式的完整短语（供正文直接引用）。"""
    text = tidy(getattr(it, "text", it))
    text = money(pct(text))
    date, _, has_year = lead_date(text)
    body = digest(it, budget=budget)
    if not body:
        return ""
    if date and not has_year:
        ty = time_cn(getattr(it, "time", ""))
        y = re.match(r"^((?:19|20)\d{2})", ty)
        date = f"{y.group(1)} 年 {date}" if y else date
    if not date:
        date = time_cn(getattr(it, "time", ""))
    # 正文内部的日期与句首日期年份不一致时，以正文日期为准（否则会读成两件事）
    m_in = re.search(r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月", body)
    m_dt = re.match(r"^((?:19|20)\d{2})", date or "")
    if m_in and m_dt and m_in.group(1) != m_dt.group(1):
        date = f"{m_in.group(1)} 年 {int(m_in.group(2))} 月"
        has_year = True
    # 日期里已含月份时，正文不再重复“M 月 M 日”，也不重复同年的完整日期
    ym_ = re.match(r"^((?:19|20)\d{2})\s*年(?:\s*(\d{1,2})\s*月)?", date or "")
    if ym_:
        if ym_.group(2):
            body = re.sub(r"^\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?[，,]?\s*", "", body).strip(_TRAIL_PUNCT)
        y = ym_.group(1)
        mo = ym_.group(2)
        body = re.sub(rf"^公司于\s*{y}\s*年\s*\d{{1,2}}\s*月"
                      rf"(?:\s*\d{{1,2}}\s*日)?\s*", "公司", body)
        body = re.sub(rf"^(?:截至|自|于|到)?\s*{y}\s*年\s*\d{{1,2}}\s*月"
                      rf"(?:\s*\d{{1,2}}\s*日)?\s*[，,]?\s*", "", body).strip(_TRAIL_PUNCT)
        if mo:
            # 句中重复同年同月的完整日期 → “该日”，避免“2025 年 3 月，公司股票自 2025 年 3 月 14 日起…”
            body = re.sub(rf"{y}\s*年\s*{int(mo)}\s*月\s*\d{{1,2}}\s*日", "该日", body)
    if not body:
        return ""
    out = f"{date}，{body}" if date and not body.startswith(date) else body
    return space_out(out).strip(_TRAIL_PUNCT)


# ------------------------------------------------------------------ 主题分类
THEMES: list[tuple[str, re.Pattern]] = [
    ("并购与重组", re.compile(r"收购|并购|重组|重整|置入|置出|注入|剥离|出售|转让|资产置换|吸收合并")),
    ("融资与资本运作", re.compile(r"定增|非公开|向特定对象|配股|可转债|公司债|中票|超短融|债券|发行股份|"
                             r"募资|募集|授信|担保|借款|H 股|分拆|上市融资")),
    ("海外与国际化", re.compile(r"境外|海外|国外|新加坡|越南|老挝|柬埔寨|缅甸|印尼|马来|美国|巴西|非洲|"
                            r"海外基地|出口")),
    ("产能与项目", re.compile(r"产能|扩产|投产|达产|新建|建设|项目|基地|养殖场|工厂|生产线|育肥|种源")),
    ("股权与股东回报", re.compile(r"回购|股权激励|员工持股|增持|减持|分红|派现|权益分派|质押")),
    ("主业转型", re.compile(r"转型|更名|变更|控制权|易主|借壳|跨界|聚焦|退出|剥离")),
]

NOISE_NONSTRAT_RE = re.compile(
    r"利润分配|权益分派|每 10 股|派发现金红利|归母净利润|归属于上市公司股东的净利润|"
    r"营业收入 ?[为\d]|资产负债率 ?[为\d]|实现营业收入|现金管理|闲置自有资金|付息兑付")

_NOISE_HEAD_RE = re.compile(r"^(?:报告期末|报告期|截至|同比|环比|其中|同日)")


def themes_of(it) -> list[str]:
    """一条事实归到哪几个战略主题（可能多主题）。"""
    t = tidy(getattr(it, "text", it))
    return [name for name, pat in THEMES if pat.search(t)]


def is_strategy_noise(it) -> bool:
    """是否为“非战略”条目（业绩复述、分红派现、现金管理、会计政策、合同条款），战略段落应过滤掉。"""
    t = tidy(getattr(it, "text", it))
    if NOISE_NONSTRAT_RE.search(t) and not MARQUEE_RE.search(t):
        return True
    # 会计政策/估计变更、合同条款、公司自评话术都不是战略动作
    if re.search(r"会计政策|会计估计|计量模式|追溯调整|核算方法|折旧年限|合并范围变更|"
                 r"遵循[^，。；]{0,12}原则|享有优先[^，。；]{0,6}权|协议条款|补充协议约定", t):
        return True
    # 纯经营表现的描述（量价齐增、销量/售价同比、毛利率变化）属经营面，不是战略动作
    if re.search(r"预算目标|年度预算|经营计划|业绩目标|营业收入不低于", t):
        return True
    if re.search(r"量价齐增|量价齐升|销量同比|售价同比|毛利率(?:提升|下降|提高)|增收不增利|"
                 r"出栏量同比|存栏量同比|产能利用率", t) and not re.search(
            r"收购|并购|重组|重整|发行|募投|设立|投产|扩产|新建|股权激励|回购|转让|剥离", t):
        return True
    return False


def risk_kind(it) -> str:
    """风险条目归类，用于“风险集中在……两类”这样的归纳句。"""
    t = tidy(getattr(it, "text", it))
    table = [
        ("退市与持续经营", r"净资产为负|资不抵债|退市风险|面值退市|持续经营能力|非标意见|保留意见"),
        ("重整与债务违约", r"重整|预重整|破产|违约|逾期|展期|和解|失信|被执行"),
        ("监管与合规", r"问询函|关注函|处罚|立案|警示函|监管函|纪律处分|违规|非经营性资金占用"),
        ("股东与质押", r"质押|平仓|减持|司法处置|轮候冻结|股份被[^，。；]{0,4}(?:冻结|拍卖)"),
        ("诉讼与资产冻结", r"诉讼|仲裁|冻结|查封|拍卖|胜诉|败诉"),
        ("审计与减值事项", r"关键审计事项|减值|计提|坏账|存货跌价|商誉"),
    ]
    for name, pat in table:
        if re.search(pat, t):
            return name
    return "其他"


__all__ = ["tidy", "space_out", "money", "pct", "time_cn", "lead_date", "prune_parens",
           "digest", "phrase", "themes_of", "is_strategy_noise", "risk_kind", "THEMES", "shorten"]
