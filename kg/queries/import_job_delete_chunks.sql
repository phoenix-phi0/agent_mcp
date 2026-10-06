-- 删一个导入任务的块（见 import_job_delete.sql）。
DELETE FROM import_chunk WHERE job = CAST(:job AS INTEGER)
