-- 一课草稿属于哪个任务。
SELECT job FROM import_lesson WHERE id = CAST(:draft AS INTEGER)
