-- 判默写的候选：跟这个词沾边的别的词——同汉字、同读音，或者意思（去掉等级
-- 前缀）完全一样。交给 japanese 包的「判默写」：同义词也算对、写成同读音的
-- 另一个词要说出来、同汉字的另一个读法要提示，都靠它。宁多勿少，算不算对
-- 由动词按规则定。
WITH t AS (
  SELECT id, coalesce(kanji, '') AS kanji, kana,
         trim(CASE WHEN meaning GLOB '[[]N[1-5]]*' THEN substr(meaning, 5) ELSE coalesce(meaning, '') END) AS bare
  FROM word WHERE id = CAST(:word AS INTEGER)
)
SELECT coalesce(w.kanji, '') AS kanji, w.kana, coalesce(w.meaning, '') AS meaning
FROM word w, t
WHERE w.id <> t.id
  AND ((t.kanji <> '' AND w.kanji = t.kanji)
       OR w.kana = t.kana
       OR (t.bare <> '' AND trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5)
                                      ELSE coalesce(w.meaning, '') END) = t.bare))
LIMIT 50
