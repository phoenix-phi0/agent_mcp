-- :code 的全部后续（后代），dist 是最近的距离：1 是直接解锁的。
-- 「会了这个之后，往后能学到哪些」。
WITH RECURSIVE down(code, dist) AS (
  SELECT dst, 1 FROM prereq WHERE src = :code
  UNION
  SELECT p.dst, d.dist + 1 FROM prereq p JOIN down d ON p.src = d.code
)
SELECT n.code, n.label, MIN(d.dist) AS dist
FROM down d JOIN node n ON n.code = d.code
GROUP BY n.code, n.label
ORDER BY dist, n.code
