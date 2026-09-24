-- 还没挂到知识点上的词。
--
-- 批量导入之后最该看的就是这个：挂漏了的词不会报错，但按知识点出题时
-- 永远取不到它们，等于不存在。
SELECT id, kanji, kana, meaning
FROM word
WHERE point IS NULL OR point = ''
ORDER BY id
LIMIT CAST(:条数 AS INTEGER)
