-- 去掉一课草稿的一个映射（条目、知识点里都找，找到就删）。
UPDATE import_lesson SET
  items = (SELECT coalesce(json_group_array(value), '[]') FROM
             (SELECT value FROM json_each(import_lesson.items) WHERE value <> trim(:map_code) ORDER BY key)),
  points = (SELECT coalesce(json_group_array(value), '[]') FROM
             (SELECT value FROM json_each(import_lesson.points) WHERE value <> trim(:map_code) ORDER BY key))
WHERE id = CAST(:draft AS INTEGER)
