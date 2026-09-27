# ============================================================================
# 中国农业周期性分析报告 —— LaTeX 构建
# ============================================================================
MAIN      := main
TEXDIR    := tex
DATADIR   := data/clean
LATEX     := xelatex
LATEXFLAGS := -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1

TEXSRC := $(wildcard $(TEXDIR)/*.tex)
# 生成的片段也必须算依赖：否则 scripts/*.py 重新生成 tex/gen/** 之后，
# make 会认为 main.pdf 仍是最新的（"无需做任何事"），改了内容却不重编
GENSRC := $(wildcard $(TEXDIR)/gen/*.tex) $(wildcard $(TEXDIR)/gen/profiles/*.tex)
DATSRC := $(wildcard $(DATADIR)/*.dat) $(wildcard $(DATADIR)/*.csv)

.PHONY: all pdf data profiles aux check clean distclean view fetch

all: pdf

# 两遍编译 + biber（解析交叉引用、目录与 gb7714 参考文献）
pdf: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex $(TEXSRC) $(GENSRC) $(DATSRC) refs.bib
# 第一遍允许非零退出：全新构建时 .aux 尚无交叉引用与文献标签，LaTeX 会报
# “undefined references”并以非零状态结束；此时 PDF 已写出，后续两遍会解析完毕。
# 后两遍不加 “-”，仍严格失败；最终结果由 make check 校验。
	-$(LATEX) $(LATEXFLAGS) $(MAIN)
	biber $(MAIN)
	$(LATEX) $(LATEXFLAGS) $(MAIN)
	$(LATEX) $(LATEXFLAGS) $(MAIN)

# 抓取/更新原始数据并生成 LaTeX 用数据表与分析表
data:
	.venv/bin/python scripts/fetch_sw.py
	.venv/bin/python scripts/fetch_futures.py
	.venv/bin/python scripts/fetch_hog.py
	.venv/bin/python scripts/fetch_macro.py
	.venv/bin/python scripts/fetch_companies.py
	.venv/bin/python scripts/make_dat.py
	.venv/bin/python scripts/analyze_corr.py
	.venv/bin/python scripts/make_tables.py
	.venv/bin/python scripts/make_company.py
	.venv/bin/python scripts/make_company_profiles.py
	.venv/bin/python scripts/company_stats.py

# 只重跑第二部分逐公司画像（依赖 data/raw/company/ 与 company_legacy/）
profiles:
	.venv/bin/python scripts/make_company.py
	.venv/bin/python scripts/make_company_profiles.py
	.venv/bin/python scripts/company_stats.py

# 编译产物自检：错误行、警告数、页数
check:
	@bash scripts/build_check.sh

view: pdf
	@xdg-open $(MAIN).pdf >/dev/null 2>&1 &

# 只清理中间文件，保留 PDF
clean:
	rm -f $(MAIN).aux $(MAIN).log $(MAIN).toc $(MAIN).out $(MAIN).lof \
	      $(MAIN).lot $(MAIN).fls $(MAIN).fdb_latexmk $(MAIN).synctex.gz \
	      $(TEXDIR)/*.aux
	@echo "cleaned intermediate files"

distclean: clean
	rm -f $(MAIN).pdf
