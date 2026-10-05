-- 现在能学什么：自己没掌握、而且不存在「还没掌握的前置」。
--
-- 用两层 NOT EXISTS 而不是 JOIN + GROUP BY：前者在没有 mastery 行时天然
-- 正确（没记录就是没掌握），后者要处理 NULL，容易写错。
--
-- 按依赖深度排，浅的在前——那是从根出发的最长路径，跟 kg_levels 同一套。
WITH RECURSIVE d(code, depth) AS (
  SELECT code, 0 FROM node WHERE code NOT IN (SELECT dst FROM prereq)
  UNION
  SELECT p.dst, d.depth + 1 FROM prereq p JOIN d ON p.src = d.code
)
SELECT n.code, n.label, COALESCE(MAX(d.depth), 0) AS depth
FROM node n LEFT JOIN d ON d.code = n.code
WHERE NOT EXISTS(
        SELECT 1 FROM mastery m
        WHERE m.learner = :learner AND m.point = n.code AND m.mastered = 1)
  AND NOT EXISTS(
        SELECT 1 FROM prereq e
        WHERE e.dst = n.code
          AND NOT EXISTS(
                SELECT 1 FROM mastery m2
                WHERE m2.learner = :learner AND m2.point = e.src
                  AND m2.mastered = 1))
GROUP BY n.code, n.label
ORDER BY depth, n.code
LIMIT CAST(:limit AS INTEGER)
