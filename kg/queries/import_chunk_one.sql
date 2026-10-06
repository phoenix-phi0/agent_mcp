-- 后台解析一块要的东西：块的内容，加上它所属任务的设置。
SELECT c.id AS chunk, c.job, c.seq, coalesce(c.title, '') AS title, c.body,
       j.series, j.label, j.prefix, j.level_hint, j.rewrite
FROM import_chunk c JOIN import_job j ON j.id = c.job
WHERE c.id = CAST(:chunk AS INTEGER)
