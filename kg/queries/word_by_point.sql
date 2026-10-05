-- 一个知识点下面的词。出题时从这儿取。
SELECT id, kanji, kana, meaning
FROM word
WHERE point = :point
ORDER BY id
LIMIT CAST(:limit AS INTEGER)
