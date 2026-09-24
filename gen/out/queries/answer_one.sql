-- 按主键查一条作答。
SELECT id, learner, question, course, point, given, correct, seconds
FROM answer
WHERE id = :id
