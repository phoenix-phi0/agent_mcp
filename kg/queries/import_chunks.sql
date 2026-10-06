-- 一个任务的块表：块序、标题、状态、出错原因、请过几次模型。chunk_id 给行上的
-- 「重试」带走。
SELECT id AS chunk_id, seq, coalesce(title, '') AS title, chunk_status,
       coalesce(error, '') AS error, tries
FROM import_chunk WHERE job = CAST(:job AS INTEGER)
ORDER BY seq
