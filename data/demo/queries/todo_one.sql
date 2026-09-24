-- 按主键查一条待办。
SELECT id, task, done, due
FROM todo
WHERE id = :id
