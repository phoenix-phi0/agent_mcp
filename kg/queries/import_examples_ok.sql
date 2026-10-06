-- 例句文本合不合格：空的算合格（没有例句）；否则要是 JSON 数组、每项是对象。
-- 1 = 合格。
SELECT CASE
  WHEN coalesce(trim(:examples), '') = '' THEN 1
  WHEN json_valid(:examples) AND json_type(:examples) = 'array'
       AND NOT EXISTS (SELECT 1 FROM json_each(:examples) WHERE type <> 'object') THEN 1
  ELSE 0 END
