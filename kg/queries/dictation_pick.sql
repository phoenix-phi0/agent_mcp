-- 单词默写出一个词：回 id，挑不出来回空（查一值表 得到空串）。
--
-- 参数：:learner、:direction（meaning = 看中文写日语，reading = 看汉字写读音）、
-- :level（全部 / N5..N1）、:source（random / review）、:seen（这一轮出过的词，
-- ,1,2, 的样子，新一轮是空串）。
--
-- 能出的词（pool）：
--   · 意思不空。
--   · 不是五十音：hiragana / katakana / youon / dakuon 这几个知识点下是单个
--     假名，「あ」的意思就是「あ」，没法默写。
--   · 意思是语法说明、不是词义的不出：活用形知识点（potential / volitional /
--     imperative / causative / causative-passive，意思都是「X 的可能形」这种，
--     100 条）、量词音变（counters-sound，意思是「促音＋ぽ」「连浊 ば」）、
--     意思写成「原词 + 空格 + 的…」的（「ある 的郑重说法」），和「…的礼貌形」
--     （です、ます）。「原词 + 空格 + 的」在去掉等级前缀之后看——「[N1] 的确」
--     的空格是前缀后面那个，不能算。
--   · 看汉字写读音只出有汉字、汉字跟假名不一样的（「いただく」写的就是假名）。
--   · 等级来自意思开头的 [N4]；没有前缀的词只在「全部」里出。
--
-- random：没在这个方向上练过的词优先，都练过了再随便挑。
-- review：只从错词本里挑（规则见 dictation_book.sql，这里同一段）。
WITH pool AS (
  SELECT w.id,
         CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 2, 2) ELSE '' END AS level,
         trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5) ELSE w.meaning END) AS bare
  FROM word w
  WHERE trim(coalesce(w.meaning, '')) <> ''
    AND coalesce(w.point, '') NOT IN ('hiragana', 'katakana', 'youon', 'dakuon',
        'potential', 'volitional', 'imperative', 'causative', 'causative-passive',
        'counters-sound')
    AND (:direction = 'meaning'
         OR (trim(coalesce(w.kanji, '')) <> '' AND w.kanji <> w.kana))
),
last_wrong AS (
  SELECT word, max(id) AS wid
  FROM word_attempt
  WHERE learner = :learner AND direction = :direction AND correct = 0
  GROUP BY word
),
book AS (
  SELECT lw.word
  FROM last_wrong lw
  WHERE (SELECT count(*) FROM word_attempt a
          WHERE a.learner = :learner AND a.direction = :direction
            AND a.word = lw.word AND a.id > lw.wid
            AND a.correct = 1 AND a.hinted = 0) < 2
),
done AS (
  SELECT DISTINCT word FROM word_attempt
  WHERE learner = :learner AND direction = :direction
)
SELECT p.id
FROM pool p
WHERE p.bare <> ''
  AND ' ' || p.bare NOT GLOB '*[^ ] 的*'
  AND p.bare NOT LIKE '%的礼貌形'
  AND (:level = '全部' OR p.level = :level)
  AND instr(:seen, ',' || p.id || ',') = 0
  AND (:source <> 'review' OR p.id IN (SELECT word FROM book))
ORDER BY CASE WHEN :source = 'random' AND p.id IN (SELECT word FROM done) THEN 1 ELSE 0 END,
         random()
LIMIT 1
