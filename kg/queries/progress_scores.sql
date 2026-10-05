-- 学习进度页「掌握得分」那张表：每个打过分的知识点一行，当前分、跟上一次
-- 比的变化、最近一次打分的时间。分低的在前——薄弱的点先看到。
--
-- 当前分、上一次都按 id 取（同一秒打两次分，at 一样）。只打过一次的点
-- 没有「上一次」，变化写「首次」；跟上一次一样（手工 /score/add 记了同分）
-- 写「±0」。减号用全角「−」，跟加号对得齐、不会被看成连字符。
WITH cur AS (
  SELECT s.point, s.value, s.at, s.id,
         (SELECT p.value FROM score p
           WHERE p.learner = s.learner AND p.point = s.point AND p.id < s.id
           ORDER BY p.id DESC LIMIT 1) AS prev
  FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
)
SELECT c.point AS code,
       n.label,
       c.value,
       c.prev,
       CASE WHEN c.prev IS NULL THEN '首次'
            WHEN c.value > c.prev THEN '+' || (c.value - c.prev)
            WHEN c.value < c.prev THEN '−' || (c.prev - c.value)
            ELSE '±0' END AS delta,
       c.at
FROM cur c
JOIN node n ON n.code = c.point
ORDER BY c.value, c.id DESC
