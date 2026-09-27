#!/usr/bin/env bash
# 编译产物自检：错误行、警告数、页数。用法：bash scripts/build_check.sh
set -u
LOG=main.log
PDF=main.pdf
[ -f "$LOG" ] || { echo "未找到 $LOG，请先执行 make pdf"; exit 1; }

echo "== 错误（! 开头，或 -file-line-error 的 file:line 形式）=="
if grep -nE "^! |\.tex:[0-9]+: (Extra alignment tab|Undefined control sequence|Missing|LaTeX Error|Emergency stop|Package .* Error)" "$LOG"; then
  :
else
  echo "（无）"
fi

echo "== Overfull / Underfull =="
echo "Overfull hbox : $(grep -c 'Overfull \\hbox' "$LOG" || true)"
echo "Overfull vbox : $(grep -c 'Overfull \\vbox' "$LOG" || true)"
echo "Underfull vbox: $(grep -c 'Underfull \\vbox' "$LOG" || true)"

echo "== 图表数据与坐标轴范围（裁切检查）=="
if [ -x .venv/bin/python ]; then
  .venv/bin/python scripts/check_axis_ranges.py
else
  python3 scripts/check_axis_ranges.py
fi

echo "== 生成文本中的悬空转义（反斜杠后紧跟中文，通常是截断把转义切一半）=="
if grep -rnP '\(?=[^\x00-\x7F])' tex/gen/*.tex tex/gen/profiles/*.tex 2>/dev/null | head -20 | grep .; then
  echo "^^ 需修正：截断前先转义会把 %、& 等切半，务必先截断再转义"
else
  echo "（无）"
fi

echo "== 画像正文文字自检（省略号 / 残句 / 公告搬运痕迹 / 段内重复）=="
if [ -x .venv/bin/python ]; then
  .venv/bin/python scripts/check_profile_text.py 2
else
  python3 scripts/check_profile_text.py 2
fi

echo "== 未定义引用 / 标签 =="
echo "引用未解析   : $(grep -c -E 'Reference .* undefined|Citation .* undefined|There were undefined references' "$LOG" || true)"
echo "（另有字体形状 undefined 提示，属中文斜体缺字形，不影响排版：$(grep -c 'Font shape.*undefined' "$LOG" || true) 处）"
echo "multiply def.: $(grep -c 'multiply defined' "$LOG" || true)"

echo "== 版面越界（逐页像素检查，需要 pdftoppm + Pillow）=="
if [ -f "$PDF" ] && command -v pdftoppm >/dev/null 2>&1; then
  PY=python3
  [ -x .venv/bin/python ] && PY=.venv/bin/python
  "$PY" scripts/check_margins.py "$PDF" 100 | tail -n 20
else
  echo "（跳过：缺少 pdftoppm 或 PDF）"
fi

echo "== 页数 =="
pdfinfo "$PDF" 2>/dev/null | grep Pages || echo "（无法读取 PDF）"
