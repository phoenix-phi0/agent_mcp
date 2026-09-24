-- 错题本列表。带上 learner 供界面跳转用。
SELECT learner, question, course, point, times, last_at
FROM wrong
ORDER BY learner DESC
LIMIT CAST(:条数 AS INTEGER)
