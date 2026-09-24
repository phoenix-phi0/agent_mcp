-- 待办列表。取全部列，编辑时整行拷进表单。
SELECT id, task, done, due
FROM todo
ORDER BY id DESC
LIMIT CAST(:条数 AS INTEGER)
