-- 一个人在一个知识点上的全部打分，从早到晚——看掌握程度是怎么变的。
--
-- 按 id 排，不按 at：同一秒里的两次，at 一样，按 at 排先后不确定。
SELECT value, at
FROM score
WHERE learner = :learner AND point = :point
ORDER BY id
