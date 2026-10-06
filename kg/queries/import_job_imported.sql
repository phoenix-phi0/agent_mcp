-- 确认导入之后记下时间和导入报告（JSON 文本）。
UPDATE import_job SET imported = datetime('now', 'localtime'), report = :report
WHERE id = CAST(:job AS INTEGER)
