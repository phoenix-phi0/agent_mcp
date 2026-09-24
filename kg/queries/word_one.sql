-- 按主键查一条单词。
SELECT id, kanji, kana, meaning, point
FROM word
WHERE id = :id
