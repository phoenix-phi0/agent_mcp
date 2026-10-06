-- 一课挂着的条目，带条目所属知识点的名字。按 rank、编号排。
-- 新教材的课还可能直接挂知识点（lesson_point）：排在条目后面，条目一格写知识点名。
SELECT code, label, point_label FROM (
  SELECT 0 AS ord, il.rank, i.code, i.label, coalesce(n.label, i.point) AS point_label
  FROM item_lesson il
  JOIN item i ON i.code = il.item
  LEFT JOIN node n ON n.code = i.point
  WHERE il.lesson = :lesson
  UNION ALL
  SELECT 1, 0, n.code, '（整个知识点）', n.label
  FROM lesson_point lp JOIN node n ON n.code = lp.point
  WHERE lp.lesson = :lesson
)
ORDER BY ord, rank, code
