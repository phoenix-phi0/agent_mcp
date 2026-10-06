-- 教材页「系列」下拉的选项：sort ≥ 0 的系列，按 sort、编号排。{value, label}
-- 是「选项来自」要的样子（tools/ui.py）。只有一个系列时也照样给（下拉只有一项）。
SELECT code AS value, label FROM series WHERE sort >= 0 ORDER BY sort, code
