-- 一课挂着的条目，带条目所属知识点的名字。按 rank、编号排。
SELECT i.code, i.label, coalesce(n.label, i.point) AS point_label
FROM item_lesson il
JOIN item i ON i.code = il.item
LEFT JOIN node n ON n.code = i.point
WHERE il.lesson = :lesson
ORDER BY il.rank, i.code
