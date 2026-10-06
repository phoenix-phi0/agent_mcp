-- 一课草稿现在的映射，一行一个：条目还是知识点、编号、名称（条目带所属知识点）。
-- 编辑页的映射表，map_code 给行上的「去掉」带走。
SELECT '条目' AS map_kind, i.code AS map_code,
       i.label || coalesce('（属于 ' || n.label || '）', '') AS map_label
FROM import_lesson d, json_each(d.items) je
JOIN item i ON i.code = je.value LEFT JOIN node n ON n.code = i.point
WHERE d.id = CAST(:draft AS INTEGER)
UNION ALL
SELECT '知识点', n.code, n.label
FROM import_lesson d, json_each(d.points) je
JOIN node n ON n.code = je.value
WHERE d.id = CAST(:draft AS INTEGER)
