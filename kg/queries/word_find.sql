-- 导入时查这个词在不在。
--
-- 按「汉字 + 假名」认同一个词：光看假名会把同音词当成一个（「はし」是桥
-- 也是筷子），光看汉字则漏掉没有汉字的词。
--
-- COALESCE 是因为没有汉字的词那一列是 NULL，而 NULL = NULL 在 SQL 里不
-- 成立——直接比的话，每导一次都会新增一条。
SELECT id FROM word
WHERE COALESCE(kanji, '') = COALESCE(:kanji, '') AND kana = :kana
