-- 更新一条单词。id 随编辑表单一起提交（列表点编辑时整行拷进去的）。
UPDATE word SET
  kanji = NULLIF(:kanji, ''),
  kana = :kana,
  meaning = :meaning,
  point = NULLIF(:point, '')
WHERE id = :id
