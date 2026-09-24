-- 按主键查一条笔记。
SELECT id, title, body, pinned
FROM note
WHERE id = :id
