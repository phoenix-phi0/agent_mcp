-- 学习者列表。带上 code 供界面跳转用。
SELECT code, name, level, started
FROM learner
ORDER BY code DESC
LIMIT CAST(:limit AS INTEGER)
