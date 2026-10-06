-- 删一个导入任务本身（草稿课、块已经删了）。
DELETE FROM import_job WHERE id = CAST(:job AS INTEGER)
