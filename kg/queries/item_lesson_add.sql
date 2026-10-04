-- 把一课挂到一个条目上。两头都得存在，不存在就影响 0 行，导入器记下来
-- 报告——拼错一个编号不该让整批挂接都进不去，但也不能悄悄少一条。
-- 同一对已经挂过的也是 0 行（文件里重复写了一行）。
INSERT INTO item_lesson(item, lesson, rank)
SELECT :item, :lesson, CAST(:rank AS INTEGER)
WHERE EXISTS (SELECT 1 FROM item WHERE code = :item)
  AND EXISTS (SELECT 1 FROM lesson WHERE code = :lesson)
  AND NOT EXISTS (SELECT 1 FROM item_lesson WHERE item = :item AND lesson = :lesson)
  AND :rank <> '' AND :rank NOT GLOB '*[^0-9]*'
