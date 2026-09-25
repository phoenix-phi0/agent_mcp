-- 一个人在一个知识点上的现状，带上按达标线算出来的结论。
--
-- 达标线从参数来，不从节点上取：同一张图，严格模式和宽松模式该用不同的
-- 线，考前和平时也不一样。
--
-- 正确率用整数百分比算，避免浮点数比较：right * 100 / total 是整除，
-- 8/10 得 80，正好跟「正确率 80」比得上。
SELECT
  right,
  total,
  mastered,
  CASE WHEN total > 0 THEN right * 100 / total ELSE 0 END AS rate,
  CASE WHEN total >= CAST(:min_count AS INTEGER)
        AND total > 0
        AND right * 100 / total >= CAST(:rate AS INTEGER)
       THEN 1 ELSE 0 END AS ok
FROM mastery
WHERE learner = :learner AND point = :point
