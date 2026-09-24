-- :code 的全部前置（祖先），dist 是最近的距离：1 是直接前置。
-- 「学这个之前，总共要先会哪些」。
--
-- 同一个祖先可能从几条路径到达，取最短的那条的距离。
WITH RECURSIVE up(code, dist) AS (
  SELECT src, 1 FROM prereq WHERE dst = :code
  UNION
  SELECT p.src, u.dist + 1 FROM prereq p JOIN up u ON p.dst = u.code
)
SELECT n.code, n.label, MIN(u.dist) AS dist
FROM up u JOIN node n ON n.code = u.code
GROUP BY n.code, n.label
ORDER BY dist, n.code
