-- 按主键查一条错题本。
SELECT learner, question, course, point, times
FROM wrong
WHERE learner = :learner
