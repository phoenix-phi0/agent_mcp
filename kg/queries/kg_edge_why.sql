-- kg_edge_add 拒掉一条边之后，查它为什么被拒。条件的顺序跟那条插入一致，
-- 报的是第一个不满足的。
WITH RECURSIVE reach(n) AS (
  SELECT :dst
  UNION
  SELECT p.dst FROM prereq p JOIN reach r ON p.src = r.n
)
SELECT CASE
  WHEN :src = :dst THEN '自环'
  WHEN NOT EXISTS (SELECT 1 FROM node WHERE code = :src) THEN '前置不存在'
  WHEN NOT EXISTS (SELECT 1 FROM node WHERE code = :dst) THEN '节点不存在'
  WHEN EXISTS (SELECT 1 FROM prereq WHERE src = :src AND dst = :dst) THEN '已存在'
  WHEN EXISTS (SELECT 1 FROM reach WHERE n = :src) THEN '会成环'
  ELSE '未知'
END AS reason
