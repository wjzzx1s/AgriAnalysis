# 中国农业周期性分析报告（AgriAnalysis）

基于申万行业分类（2021 版）的中国农业周期性分析，含两大部分：

1. **第一部分：农业子行业周期性与跨品种相关性**——分品种讨论供需周期（需求来自消费、
   工业原料与饲料三条链，供给分品种讨论气候、疫情、政策影响），以猪周期为基准考察
   其他养殖品种（肉牛、肉羊、禽、水产）与经济作物的相关性与传导时滞。
2. **第二部分：农业上市公司画像**——申万农林牧渔 104 家 A 股上市公司，先按行业分类做
   总体与行业层面的分析，再在各行业章（第 8—13 章）末尾的**“上市公司画像”小节**中
   对每一家公司单独成节，给出基本情况、历史股价、过去周期、
   盈利与财务、重大战略转型、历史融投资与未来潜在融资需求七个维度的画像。

数据时点为 **2026 年 9 月**：行情数据的最后一个交易日为 2026 年 9 月 24 日，
财务数据含 2026 年半年报（合并报表口径，未年化）。

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
| `tex/appendix-*.tex` | 附录：数据来源与口径、公司明细表（含 2026 半年报概览）、期货合约参数 |
| `scripts/fetch_*.py` | 数据抓取（开源财经数据接口 → `data/raw/`） |
| `scripts/make_dat.py` | 数据加工（`data/raw/` → `data/clean/*.dat` + 分析摘要） |
| `scripts/analyze_corr.py` | 相关矩阵、领先滞后、传导回归、ZigZag 分段 |
| `scripts/make_tables.py` | 第一部分表格与图表数据的 LaTeX 片段（`tex/gen/*.tex`） |
| `scripts/make_company.py` | 公司汇总表与分行业表（`data/clean/company_master.csv` 等） |
| `scripts/make_company_profiles.py` | **逐公司画像**：指标计算、股价/骨架数据、LaTeX 片段 |
| `scripts/check_margins.py` | 逐页检查 PDF 内容是否越出页边距（图片/表格 overfull 自检） |
| `scripts/build_check.sh` | `make check`：错误行、Overfull 计数、未定义引用、页数 |
| `data/raw/` | 原始数据（未入库，含 `_manifest.json` 记录接口、抓取时间、行列数；`hog_capacity_official.csv` 记录官方发布期次及其来源） |
| `data/clean/` | 作图数据 `.dat`（pgfplots 直读）、分析结果 `.csv`、`profiles/` 逐公司股价数据 |
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
```

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

- 正文中的一切数字来自 `scripts/` 产出的 CSV / `.dat`，或 `notes/` 中汇总的统计量；
  不手工填写数据。
- 图表一律用 TikZ / pgfplots 绘制，数据经 `data/clean/*.dat` 注入，不用位图截图。
- 逐公司画像的八个自然段（基本情况、历史股价、周期分析、盈利、财务、转型、
  融投资、融资需求）全部由 `scripts/make_company_profiles.py` 依数据生成；
  每家公司一小节（`\subsubsection`，源码片段在 `tex/gen/profiles/`），
  按流通市值降序排列，插入所属行业章的“上市公司画像”小节，正文不做手工单点修改。
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
13. **图表下不再输出“资料来源”一行**（用户要求）：`make_tables.py` /
    `make_company*.py` 不再写 `\srcfile{}`，口径文本保留在脚本的 `src=` 参数里备查；
    读图必需的口径（显著性阈值、颜色含义、剔除规则、时点）折进表题/图注。
14. **逐公司画像不采用浮动体**：104 张股价图若用 `figure` 浮动，
    会挤占浮动队列并造成大段空白，故画像中的图与表都用 `center` 环境就地排版。
15. **越界自检**：`python3 scripts/check_margins.py main.pdf` 逐页渲染并检查
    非白像素是否进入页边距安全区，可机器化发现图片/表格溢出（`make check` 已内置）。
