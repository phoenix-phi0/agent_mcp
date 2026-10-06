-- 编辑页「从已有的选」下拉：全部条目和知识点，{value, label}。条目在前（按所属
-- 知识点排），知识点的 label 带〔〕。
SELECT value, label FROM (
  SELECT i.code AS value, i.label || '（条目，' || i.code || '）' AS label, 0 AS g, i.point AS k
  FROM item i
  UNION ALL
  SELECT code, '〔' || label || '〕（知识点，' || code || '）', 1, code FROM node)
ORDER BY g, k, value
