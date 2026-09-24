-- 按主键查一条学习者。
SELECT code, name, level, note
FROM learner
WHERE code = :code
