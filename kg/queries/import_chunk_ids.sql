-- 一个任务的块 id，按块序。新建任务后逐块交给后台用。
SELECT id AS chunk FROM import_chunk WHERE job = CAST(:job AS INTEGER) ORDER BY seq
