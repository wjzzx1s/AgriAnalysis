# 中国农业周期性分析报告（AgriAnalysis）

基于申万行业分类（2021 版）的中国农业周期性分析，含两大部分：

1. **第一部分：农业子行业周期性与跨品种相关性**——分品种讨论供需周期（需求来自消费、
   工业原料与饲料三条链，供给分品种讨论气候、疫情、政策影响），以猪周期为基准考察
   其他养殖品种（肉牛、肉羊、禽、水产）与经济作物的相关性与传导时滞。
2. **第二部分：农业上市公司画像（近三年）**——申万农林牧渔 104 家 A 股上市公司，按行业
   分类梳理公司基本情况、周期敏感度、盈利与财务、重大战略转型、历史融投资与未来潜在
   融资需求。

## 目录结构

| 路径 | 内容 |
|---|---|
| `main.tex` | 主文件（封面 + 摘要 + 目录 + 两部分正文 + 附录） |
| `tex/preamble.tex` | 导言区：字体、版面、颜色主题、tikz/pgfplots 全局样式、自定义宏 |
| `tex/ch01-framework.tex` | 第 1 章 研究框架、申万分类口径与数据基础 |
| `tex/ch02-hog-cycle.tex` | 第 2 章 猪周期 |
| `tex/ch03-grain-oilseed.tex` | 第 3 章 粮食与油料（玉米、小麦、稻米、大豆、油脂压榨链） |
| `tex/ch04-soft-crops.tex` | 第 4 章 软商品与经济作物（白糖、棉花、苹果、红枣、花生、橡胶） |
| `tex/ch05-other-livestock.tex` | 第 5 章 其他养殖与水产（肉禽、蛋禽、牛羊、鱼） |
| `tex/ch06-correlation.tex` | 第 6 章 跨品种周期相关性与传导（以猪周期为基准） |
| `tex/ch07`–`tex/ch14` | 第二部分：总体格局与分行业公司画像、战略转型与融资 |
| `tex/appendix-*.tex` | 附录：数据来源、公司明细表、期货合约参数 |
| `scripts/fetch_*.py` | 数据抓取（akshare → `data/raw/`） |
| `scripts/make_dat.py` | 数据加工（`data/raw/` → `data/clean/*.dat` + 分析摘要） |
| `scripts/make_company_tables.py` | 公司财务/融资汇总表与 LaTeX 片段 |
| `data/raw/` | 原始数据（含 `_manifest.json` 记录接口、抓取时间、行列数） |
| `data/clean/` | 作图数据 `.dat`（pgfplots 直读）与分析结果 `.csv` |
| `tex/gen/` | 由脚本自动生成的 LaTeX 表格片段（`\input` 引用） |
| `notes/` | 接口探测报告、数据摘要（撰写正文时引用的一致口径数字） |

## 环境与构建

```bash
# 1) Python 环境（akshare 数据抓取）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python akshare pandas matplotlib

# 2) 数据：抓取 + 加工
make data                      # 依次运行 fetch_*.py 与 make_dat.py

# 3) 报告编译（xelatex 两遍，解析交叉引用与目录）
make pdf                       # 或 latexmk -xelatex main.tex
make check                     # 编译产物自检：错误行、警告数、页数
```

**编译依赖**：TeX Live（`ctex`、`tikz`/`pgfplots`/`pgfplotstable`、`booktabs`、
`tabularx`、`tcolorbox`、`zhnumber`、`siunitx`）与中文字体 **思源宋体 CN / 思源黑体 CN**
（`Source Han Serif CN`、`Source Han Sans CN`）+ 文泉驿等宽正黑。缺字体时需改
`tex/preamble.tex` 中的字体声明。**必须用 xelatex 编译**（pdflatex 无法处理中文与
fontspec）。

## 数据来源

akshare 开源接口（底层为新浪财经、东方财富、巨潮资讯网、申万宏源、大连商品交易所、
猪易数据、国家统计局、中价指数），数据截至 **2026 年 9 月**。每个数据文件的接口名、
抓取时间与行列数记录在 `data/raw/_manifest.json`。

## 写作与数据一致性约定

- 正文中的一切数字来自 `scripts/` 产出的 CSV / `.dat`，或 `notes/data_summary.md`
  中汇总的统计量；不手工填写数据。
- 图表一律用 TikZ / pgfplots 绘制，数据经 `data/clean/*.dat` 注入，不用位图截图。
- 图下 `\srcfile{}` 标注来源与口径；表用 `\datacal{}` 标注口径。
