-- 一块属于哪个任务（重试接口回刷页面用）。
SELECT job FROM import_chunk WHERE id = CAST(:chunk_id AS INTEGER)
