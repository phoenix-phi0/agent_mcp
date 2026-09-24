-- 按依赖分层：depth 是从根出发的**最长**距离。根是 0。
--
-- 取最长而不是最短：一个知识点要等它所有前置都学完才能学，决定它排在第几
-- 层的是最慢到达的那条路。按 depth 排序就是一个合法的学习顺序（拓扑序）——
-- 每条边的起点 depth 一定小于终点。
--
-- 跟 kg.json 里的「层」不是一回事：那个是按主题分组（文字 0、音韵 1……），
-- 同一层里也可能有依赖。这个是按依赖算出来的。
WITH RECURSIVE d(code, depth) AS (
  SELECT code, 0 FROM node WHERE code NOT IN (SELECT dst FROM prereq)
  UNION
  SELECT p.dst, d.depth + 1 FROM prereq p JOIN d ON p.src = d.code
)
SELECT n.code, n.label, MAX(d.depth) AS depth
FROM d JOIN node n ON n.code = d.code
GROUP BY n.code, n.label
ORDER BY depth, n.code
