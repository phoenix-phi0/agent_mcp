-- 新教材的一课挂到它列出的已有条目上（item_lesson），rank 按列出的顺序
-- （第一个是 1）。导入器先用 lesson_refs_missing 查过条目都在才调它；这里
-- 照样只挂存在的、没挂过的，同一个编号列了两次只挂一次。返回挂了几条。
INSERT INTO item_lesson(item, lesson, rank)
SELECT trim(value), :code, min(CAST(key AS INTEGER)) + 1
FROM json_each(CASE WHEN json_valid(:items) AND json_type(:items) = 'array' THEN :items
                    WHEN coalesce(:items, '') = '' THEN '[]'
                    ELSE json_array(:items) END)
WHERE trim(value) IN (SELECT code FROM item)
  AND EXISTS (SELECT 1 FROM lesson WHERE code = :code)
  AND NOT EXISTS (SELECT 1 FROM item_lesson WHERE item = trim(value) AND lesson = :code)
GROUP BY trim(value)
