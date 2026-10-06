-- 给一课草稿加一个映射：:kind 是 item 就加进 items，node 加进 points；已经有了
-- 不重复加。编号存不存在接口先用 import_code_kind 查过。
UPDATE import_lesson SET
  items = CASE WHEN :kind = 'item' AND NOT EXISTS (SELECT 1 FROM json_each(items) WHERE value = trim(:code))
               THEN json_insert(items, '$[#]', trim(:code)) ELSE items END,
  points = CASE WHEN :kind = 'node' AND NOT EXISTS (SELECT 1 FROM json_each(points) WHERE value = trim(:code))
                THEN json_insert(points, '$[#]', trim(:code)) ELSE points END
WHERE id = CAST(:draft AS INTEGER)
