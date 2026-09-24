-- 导出用：全部知识点，按学习顺序排。
--
-- depth 是从根出发的最长距离（跟 kg_levels 同一个算法），按它排就保证每个
-- 知识点排在它所有前置之后——导出的文件本身就是一份合法的学习顺序，再导入
-- 时也不会遇到先引用后定义。
--
-- LEFT JOIN：万一库里被手工改出了环，环上的节点从根走不到，没有 depth，
-- 也照样导出来（排在最前），不会悄悄丢掉。
WITH RECURSIVE d(code, depth) AS (
  SELECT code, 0 FROM node WHERE code NOT IN (SELECT dst FROM prereq)
  UNION
  SELECT p.dst, d.depth + 1 FROM prereq p JOIN d ON p.src = d.code
)
SELECT n.code, n.label, COALESCE(MAX(d.depth), -1) AS depth
FROM node n LEFT JOIN d ON d.code = n.code
GROUP BY n.code, n.label
ORDER BY depth, n.code
