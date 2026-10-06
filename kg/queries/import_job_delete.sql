-- 删一个导入任务：只删草稿。三张表分三条删（写库表一次执行一条）：这条删
-- 草稿课，接着 import_job_delete_chunks、import_job_delete_job。已经导进 lesson
-- 表的课、content/series/ 下的文件都不碰。
DELETE FROM import_lesson WHERE job = CAST(:job AS INTEGER)
