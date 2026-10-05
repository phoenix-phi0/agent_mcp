-- 作答列表。带上 id 供界面跳转用。
SELECT id, learner, question, course, point, given, correct
FROM answer
ORDER BY id DESC
LIMIT CAST(:limit AS INTEGER)
