# 中国农业周期性分析报告（AgriAnalysis）

基于申万行业分类（2021 版）的中国农业周期性分析，含两大部分：

1. **第一部分：农业子行业周期性与跨品种相关性**——分品种讨论供需周期（需求来自消费、
   工业原料与饲料三条链，供给分品种讨论气候、疫情、政策影响），以猪周期为基准考察
   其他养殖品种（肉牛、肉羊、禽、水产）与经济作物的相关性与传导时滞。
2. **第二部分：农业上市公司画像**——申万农林牧渔 104 家 A 股上市公司，先按行业分类做
   总体与行业层面的分析，再在各行业章（第 8—13 章）末尾的**“上市公司画像”小节**中
   对每一家公司单独成节，给出基本情况与主营结构、历史股价、过去周期分析、盈利情况、
   财务分析、重大战略转型、历史融投资情况与未来潜在融投资需求八个维度的画像。
   画像正文由**逐家检索的公开资料底稿驱动**（`data/facts/<代码>.yaml`，只收录有来源链接的事实），
   不是统一模板套出来的：每家公司的段落重点、引用的融资与风险事件各不相同。
   每家公司配两张图——股价与行业指数对比图、近年主要财务指标组合图
   （营业收入与归母净利润、ROE 与资产负债率、货币资金与有息负债）——
   以及关键财务指标表与历史融资/资本运作表。

数据时点为 **2026 年 9 月**：行情数据的最后一个交易日为 2026 年 9 月 24 日，
财务数据含 2026 年半年报（合并报表口径，未年化）。**第二部分（第 7—14 章）统一以
2026 年半年报作为当期财务口径**（资产负债率取 2026 年 6 月末），
2025 年半年报作为同口径对照、2023—2025 年年报作为趋势对照；
半年报未年化、种植业收入确认的季节性等口径限制在正文与图表题注中逐处标明。

## 目录结构

| 路径 | 内容 |
|---|---|
| `main.tex` | 主文件（封面 + 摘要 + 目录 + 两部分正文 + 参考文献 + 附录） |
| `tex/preamble.tex` | 导言区：字体、版面、图表样式、自定义宏（朴素排版，无彩色文字；核心结论块不使用文本框） |
| `tex/cover.tex` | 封面（只保留中文大标题、中文副标题与日期） |
| `tex/ch01-framework.tex` | 第 1 章 研究框架、申万分类口径与数据基础 |
| `tex/ch02-hog-cycle.tex` | 第 2 章 猪周期 |
| `tex/ch03-grain-oilseed.tex` | 第 3 章 粮食与油料（玉米、大豆与油脂压榨链，含饲料需求侧） |
| `tex/ch04-soft-crops.tex` | 第 4 章 软商品与经济作物（白糖、棉花、苹果、红枣、花生、橡胶） |
| `tex/ch05-other-livestock.tex` | 第 5 章 其他养殖与水产（肉禽、蛋禽、牛羊、鱼） |
| `tex/ch06-correlation.tex` | 第 6 章 跨品种周期相关性与传导（以猪周期为基准） |
| `tex/ch07`–`tex/ch14` | 第二部分：总体格局、分行业分析（含**各行业章末尾的“上市公司画像”小节**）与战略转型/融资总览 |
| `tex/gen/profiles/*.tex` | 逐公司画像片段（104 家，按行业分组），由脚本生成后 `\input` 到第 8—13 章的“上市公司画像”小节 |
| `tex/ch15-conclusion.tex` | 结论与启示（第二部分末章，编号自动连续） |
| `tex/appendix-*.tex` | 附录：数据来源与口径、公司明细表（画像总表为 2026 年半年报口径）、期货合约参数 |
| `scripts/fetch_*.py` | 数据抓取（开源财经数据接口 → `data/raw/`） |
| `scripts/make_dat.py` | 数据加工（`data/raw/` → `data/clean/*.dat` + 分析摘要） |
| `scripts/analyze_corr.py` | 相关矩阵、领先滞后、传导回归、ZigZag 分段 |
| `scripts/make_tables.py` | 第一部分表格与图表数据的 LaTeX 片段（`tex/gen/*.tex`） |
| `scripts/make_company.py` | 公司汇总表与分行业表（`data/clean/company_master.csv` 等） |
| `scripts/make_company_profiles.py` | **逐公司画像**：指标计算、对比统计（行业排名/中位数）、画像上下文、LaTeX 片段 |
| `scripts/company_digest.py` | **提炼层**：底稿公告语 → 报告语（去公文壳、去程序语、子句择优、无省略号收缩） |
| `scripts/company_text.py` | 画像正文撰写：由事实底稿 + 指标组合成八个维度（按公司类型选择表述，避免模板化） |
| `scripts/company_charts.py` | 画像图表：股价与行业指数对比图、近年主要财务指标组合图 |
| `scripts/company_facts.py` | 事实底稿的读取、校验与检索（`data/facts/*.yaml`） |
| `scripts/fetch_balance.py` | 抓取资产负债表与现金流量表关键科目（货币资金、有息负债、借款与偿债现金流） |
| `scripts/make_probe_tex.py` | 抽取若干公司拼成独立测试文档（`_probe.tex`），用于快速校验画像版式 |
| `scripts/company_stats.py` | 汇总第二部分正文所需的统计量 → `notes/company_stats_h1.md`（正文数字的唯一来源） |
| `scripts/check_margins.py` | 逐页检查 PDF 内容是否越出页边距（图片/表格 overfull 自检） |
| `scripts/check_profile_text.py` | 画像正文文字自检：省略号、残句、公告搬运痕迹、段内重复、段落长度 |
| `scripts/build_check.sh` | `make check`：错误行、Overfull 计数、正文文字自检、未定义引用、页数 |
| `data/raw/` | 原始数据（未入库，含 `_manifest.json` 记录接口、抓取时间、行列数；`hog_capacity_official.csv` 记录官方发布期次及其来源） |
| `data/clean/` | 作图数据 `.dat`（pgfplots 直读）、分析结果 `.csv`、`profiles/` 逐公司股价与财务作图数据 |
| `data/facts/` | **逐公司事实底稿**（`<6位代码>.yaml`，格式见 `SCHEMA.md`）：104 家公司全覆盖、共 3368 条事实、503 条融资历史条目，只收录有来源 URL 的事实 |
| `tex/gen/` | 由脚本自动生成的 LaTeX 片段（`\input` 引用），`tex/gen/profiles/` 为逐公司片段 |
| `notes/` | 接口探测报告、数据摘要、逐公司画像生成摘要 |

## 环境与构建

```bash
# 1) Python 环境（数据抓取）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python akshare pandas numpy matplotlib pillow

# 2) 数据：抓取 + 加工（含逐公司画像）
make data                      # 依次运行 fetch_*.py、make_*.py、analyze_corr.py
make profiles                  # 只重跑公司表与逐公司画像（快）

# 3) 报告编译（xelatex 三遍 + biber）
make pdf                       # 或 latexmk -xelatex main.tex
make check                     # 编译产物自检：错误行、Overfull 数、越界页、页数

# 4) 只出第一部分（农业子行业周期性分析，ch01--ch06）的单册 PDF
make part1                     # 产出 main-part1.pdf；正文 \input 与 main.tex 同一批文件
```

**主报告与第一部分分册的关系**：`main.tex` 为全报告（527 页）；
`main-part1.tex` 只收录封面 + 摘要（第一部分口径，见 `tex/abstract-part1.tex`）+
目录 + 图表目录 + 第一部分（ch01--ch06）+ 参考文献，编译为 `main-part1.pdf`（42 页）。
两者正文来自同一批 `tex/ch0*.tex` 与 `tex/gen/*.tex`，不复制、不改写正文，
因此第一部分的章号、节号、图表编号与页码在分册中与主报告完全一致；
仅前置部分与收录范围不同。分册的摘要删去了“第二部分的主要发现”（见另一册），
并去掉了指向第二部分章节的交叉引用（分册中不存在该标签）。

**编译依赖**：TeX Live（`ctex`、`tikz`/`pgfplots`/`pgfplotstable`、`booktabs`、
`tabularx`、`tcolorbox`、`zhnumber`、`siunitx`）与中文字体 **思源宋体 CN / 思源黑体 CN**
（`Source Han Serif CN`、`Source Han Sans CN`）+ 文泉驿等宽正黑。缺字体时需改
`tex/preamble.tex` 中的字体声明。**必须用 xelatex 编译**（pdflatex 无法处理中文与
fontspec）。

## 数据来源

价格数据（期货主力连续、生猪现货与产业指标）、申万行业分类与成分股、
上市公司定期报告与公告、国家统计局宏观数据，全部来自公开渠道，
经脚本抓取后落盘到 `data/raw/`（未入库，约 50MB），再由脚本清洗为
`data/clean/` 下的分析表与作图数据。数据时点为 **2026 年 9 月**。

`data/raw/company_legacy/` 存放早期脚本产出的 `zygc`（主营构成）与 `gdhs`（股东户数）数据。
其中 **`zygc` 现由逐公司画像使用**（收入构成与主营结构变化的判断依据，最新期次为
2026 年半年报），该数据依赖同花顺主营构成口径、当前抓取流程未包含，需保留文件；
`gdhs` 仍未使用，仅作留档。

`data/raw/_manifest.json` 已入库，记录每个数据文件的接口名、行数、列数、字节数与抓取时间。
清单若因多进程并发损坏，可用 `scripts/fix_manifest.py` 扫描重建（幂等）。

## 写作与数据一致性约定

- **缺失值一律不写作 0**：清洗阶段把接口/官方记录里的 0 占位（如月度期次无
  猪肉产量、生猪存栏、生猪出栏）转为空值，`make_tables.py` 的 `fmt()` 统一渲染为
  `\nodata`（“—”）。
- **表格题注置顶**：`make_tables.py` 生成的短表把 `\caption`/`\label` 写在表格之前；
  longtable 的题注落在表体内首行。
- 正文中的一切数字来自 `scripts/` 产出的 CSV / `.dat`，或 `notes/` 中汇总的统计量；
  不手工填写数据。第二部分的正文统计量统一取自 `notes/company_stats_h1.md`
  （由 `scripts/company_stats.py` 生成）。
- **图表编号与目录**：图表按章编号（`\numberwithin{figure/table}{section}`，
  正文为“图 7-1”“表 7-1”，附录自动变为“表 A-1”），题注统一为“编号 标题”两行居中式样
  （`\captionsetup` 见 `tex/preamble.tex`），表格题注一律置于表格**上方**；
  `main.tex` 中的 `\listoffigures`/`\listoftables` 生成图目录与表目录，
  与目录并列。逐公司画像的 104 张股价图、104 张财务指标组合图
  （上排：营业收入与归母净利润、ROE 与资产负债率；下方宽带面板：货币资金/有息负债为左轴柱状、
  经营活动现金流净额为其右轴的蓝点折线），
  以及关键财务指标表与历史融资/资本运作表（有事实底稿的公司才有）也全部编号并进入图表目录；
  附录 B 另有债务结构与滚动偿付压力长表（`tab:company-financing`）。
- 图表一律用 TikZ / pgfplots 绘制，数据经 `data/clean/*.dat` 注入，不用位图截图。
- 逐公司画像的八个维度由 `scripts/company_text.py` 生成，输入有三类：
  （1）`data/facts/<代码>.yaml` 事实底稿——沿革、股权与控制权、融资历史、风险事件、
  战略动作、融资需求线索，每条都带来源链接（链接保存在底稿内，报告中不输出）；
  （2）财务与行情指标（`data/clean/company_profiles.csv`）；
  （3）对比统计——三级行业内的排名与全样本中位数。
  因此**同一句话不会出现在所有公司身上**：段落构成随公司类型
  （重整/高杠杆亏损/扩张/稳态/保壳）变化，事实条目本身也是逐家不同的。
  每家公司一小节（`\subsubsection`，源码片段在 `tex/gen/profiles/`），
  按流通市值降序排列，插入所属行业章的“上市公司画像”小节，正文不做手工单点修改。
- **画像正文的提炼层**：底稿条目多取自公告原文，不能直接搬进正文。
  `scripts/company_digest.py` 把一条底稿变成一句报告语：去掉公文壳
  （《关于…的公告》→ 事项本身）、程序语（文号、登记、保荐与承销、董事会/监事会届次）、
  与财务表重复的报表明细，再在子句间择优（重大事件与金额优先，列举残段、纯金额片段降权），
  最后在子句边界上收缩到字数预算——**输出里不出现省略号**。
  段落生成器只管“选哪几条、怎样归纳”，切句与措辞统一交给提炼层；
  新增底稿字段时应在这里加清洗规则，不要在段落代码里做字符截断。
- **正文文字自检**：`make check` 会运行 `scripts/check_profile_text.py`，逐家公司检查正文与表格
  中的省略号、残句、公告搬运痕迹、段内重复与段落长度。命中即视为错误，
  须回到提炼层修规则后重新 `make profiles`，不手工改 `tex/gen/`。
- **未来融资需求的两个量化口径**（正文逐家给出，并汇总到第 14 章）：
  `短期债务缺口 = 期末短期债务 − 货币资金`（滚动偿付压力）与
  `年化经营缺口 = 半年归母净利润 × 2`（维持当期盈利水平的现金消耗）。
  两者都是压力情形下的静态估算，用于公司之间的横向比较，不等于预测的融资规模；
  图中与表中如需表示缺失值，`.dat` 里写 `nan`（pgfplots 会跳过该点），不得写作 0。
- **口径标注规则**：凡使用半年度数据的结论，一律写明“（未年化）”或“半年报口径”；
  凡引用年报数据作对照，一律写明“（年报对照/趋势对照）”，
  不与半年报数据直接并列比较。
- 官方公开发布的最新产业数据（如 2025 年年度与 2026 年的能繁母猪存栏）在
  `data/raw/hog_capacity_official.csv` 中逐行记录来源，由 `make_dat.py` 并入
  `data/clean/hog_capacity_recent.csv` 与产能作图序列；akshare 接口未覆盖的期次
  一律以此文件补齐，不直接写进正文。

## 编译注意事项（踩过的坑）

1. **pgfplots 选项顺序**：`agri axis` 样式内含 `width/height`，局部 `width/height`
   必须写在 `agri axis` **之后**，否则被样式覆盖，并排子图会溢出页边距。
2. **`yticklabels from table` 要求表头是真实表头行**：`.dat` 首行不能写成
   `# i rho label`（注释会被跳过），须写成 `i rho label`；按索引访问的 `.dat`
   可继续用 `#` 注释首行。
3. **脚本生成的正文里 `%` 必须写成 `\%`**：LaTeX 中 `%` 是注释符，
   脚本拼出的“\num{5}\%”若漏掉反斜杠，会**截断该段之后的全部文字**
   （`make_company_profiles.py` 中用 `esc_pct()` 统一处理）。
4. **f-string 里的 `\ref{...}` 要把花括号写成 `{{...}}`**：
   否则 `{sec:hog}` 被当作 f-string 插值表达式，直接报语法错误。
5. **`\thepart` 在 ctexart 下是罗马数字**（I、II），`\zhnumber{\thepart}` 会得到
   “零”，出现“第零部分”。部分标题必须用 `\zhnumber{\arabic{part}}`。
6. **两部分之间要分页**：`\titleclass{\part}{page}[\section]` 使 `\part` 另起一页；
   原来的 `straight` 类会让第二部分标题紧接第一部分末尾。
7. **目录页码宽度**：本报告页码超过三位数，`\@pnumwidth` 默认 1.55em 会使目录页码
   溢出右边界约 1.2pt，需在导言区改写 `\@pnumwidth`/`\@tocrmarg`。
8. **页眉高度**：`\setlength{\headheight}{24pt}`，否则 fancyhdr 每页报警告。
9. **`\num{}` 不能含斜杠**：`\num{2025/26}` 会触发 siunitx 错误，需写成纯文本。
10. **`\verb` 不能出现在命令参数里**（如 `\srcfile{}`、表格单元格内），
    改用 `\texttt{}` 并把下划线写成 `\_`。
11. **构建时不要把 make 的输出接到 `| head`**：SIGPIPE 会在 `\end{document}`
    前杀死 xelatex，导致 `main.bcf` 截断、biber 报 “malformed”，
    参考文献全部变成未解析。请重定向到日志文件后再 grep。
12. **长表（longtable）宽度**：表格列数多时用 `\scriptsize` +
    `\setlength{\tabcolsep}{2pt}`；普通 `table` 由 `make_tables.py` 统一包
    `\begin{adjustbox}{max width=\textwidth}`——**只在超出版心时缩放**。
    早期用 `\resizebox{\textwidth}{!}{...}` 会把窄表放大到版心宽，
    使表格文字大于正文（报告规则：表格字号不得超过正文）。
13. **画像后面不输出任何“资料来源”**（用户要求，2026-09）：正文既不用脚注，也不列
    小节末清单——`company_text.src_block()` 现在恒返回空串（原实现与踩过的坑保留在
    `_src_block_disabled()` 里备查）。来源并未丢失：逐条 URL 仍在事实底稿
    `data/facts/<代码>.yaml` 的 `source` 字段中，报告层面的口径说明见第 7 章
    “农业上市公司画像的数据来源与用途”表。
    历史教训（若要恢复清单请照此做）：脚注方案对长 URL 是灾难——百分号编码的链接是
    不可断行的整块 token（实测单条溢出 601pt > 版心 595pt，一页曾堆 11 个脚注），
    清单方案必须给每个 URL 每 10 个字符插 `\allowbreak{}` 才能折行。
14. **逐公司画像不采用浮动体**：104 张股价图若用 `figure` 浮动，
    会挤占浮动队列并造成大段空白，故画像中的图与表都用 `center` 环境就地排版。
    代价是图形分页要自己管：财务组合图由**两个** `tikzpicture`（上排 groupplot +
    下方宽面板）组成，LaTeX 会在两张图之间分页（探针里实测：上排落在第 2 页、
    下方面板与题注落在第 3 页），所以整张图连同题注必须包进
    `\begin{minipage}{\textwidth}\centering ... \end{minipage}`；
    不可分页的整块图形会把页面底部留白推大，用
    `.venv/bin/python scripts/check_blank.py main.pdf` 量化（列出底部留白最大的页）。
15. **越界自检**：`python3 scripts/check_margins.py main.pdf` 逐页渲染并检查
    非白像素是否进入页边距安全区，可机器化发现图片/表格溢出（`make check` 已内置）。
16. **Python 模板串不要用 `str.format()`**：行业周期定位的模板里含 `\ref{sec:hog}`
    这类花括号，`format()` 会把它当占位符并抛 `KeyError`——改用 `str.replace("{tail}", ...)`。
17. **事实底稿里的文本要转义**：底稿由检索得到，含 `%`、`_`、`&`、`#`、`$` 等字符
    （尤其 URL），进入 LaTeX 前必须过一遍转义（`company_text.tesc`）；
    摘录截断（`company_text.cut`）要先找标点再切，否则会出现“1,850.0……”“支……”
    这类切在数字/词中间、读起来像坏掉的片段；切完还要去掉末尾半截数字。
18. **“借壳”这类关键词要排除否定表述**：底稿里会出现“不构成借壳上市”，
    直接用 `in` 判断会把公司误判为借壳上市；判定需用排除 `不/非/未` 的正则。
19. **股价阶段与事件对齐要按月比对**：只按年份匹配会把阶段之外的事件算作“时间上重合”
    （例如事件在 2026-09，阶段止于 2026-06），且应只在含动作词
    （收购/重整/转让/控制权/定增……）的条目中挑选事件。
20. **名次用 `\zhnumber{}`，不要加空格**：`第\zhnumber{11}位` 渲染为“第十一位”；
    写成 `第 \zhnumber{11} 位` 会在中文里多出一个空格（渲染成“第 十一位”），
    中文行文按规范不加空格。另外“排第 X 位”必须写明排序方向
    （如“按 ROE 由高到低排第二位”），否则读者会把第 2 名误读成绩优。
21. **轴标签字号必须显式设定**：`tick label style={font=\tiny}` 只作用于刻度数字，
    坐标轴标签（`ylabel`）会退回正文字号（约 10.5pt），于是图里出现“刻度 7pt、
    “亿元”10.5pt”的失衡观感（用户会直接指出“旁边的亿元太大”）。每个 `axis` 都要写
    `ylabel style={font=\tiny}`。
22. **同一张图里量级差很多的序列，用右轴，不要同轴硬画**：货币资金/有息负债是数十亿量级，
    经营活动现金流净额常在个位数，同轴时蓝点被压在零线上，读者看不出它属于哪条序列。
    做法：柱状图用左轴，现金流另起一个 `axis`，`axis y line*=right, axis x line*=none,
    xtick=\empty`；两个 axis 都写 `scale only axis`（此时 `width`/`height` 指**绘图区**，
    与标签宽度无关），右轴用 `at={(左轴名.south east)}, anchor=south east` 对齐，
    绘图区就会严格重合。右轴不要再写 `ylabel`（图例里写“（右轴，亿元）”即可），
    否则右侧要多留约 0.5cm，整图会顶出版心。
23. **宽度预算要按“最坏一行”算**：上排两个 6.85cm 面板 + 0.60cm 间隔 = 14.30cm，
    加上左侧刻度与轴标签约 1.45cm 正好 15.75cm（版心 15.8cm）；一旦给右轴加标签
    （约 0.7cm）或把面板加宽到 7.00cm，就会超出 1cm 左右。改宽度后先在探针里
    编译一次看 `Overfull hbox` 的 pt 数，比全量编译快得多。
24. **快速版式校验**：改画像排版后不必全量编译（104 家公司），
    用 `.venv/bin/python scripts/make_probe_tex.py <代码> <代码> ...` 生成 `_probe.tex`
    单独编译，再 `pdftoppm` 渲染成图做目视检查。
