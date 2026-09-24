-- 笔记列表。取全部列，编辑时整行拷进表单。
SELECT id, title, body, pinned, created_at
FROM note
ORDER BY id DESC
LIMIT CAST(:条数 AS INTEGER)
