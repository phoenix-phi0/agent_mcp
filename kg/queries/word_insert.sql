-- 新建一条单词。
-- id 是自增主键，不在这里给。
INSERT INTO word(kanji, kana, meaning, point)
VALUES(NULLIF(:kanji, ''), :kana, :meaning, NULLIF(:point, ''))
