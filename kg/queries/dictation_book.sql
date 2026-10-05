-- 错词本：某人在某方向上的错词，可按等级筛。dictation_pick.sql 里复习模式
-- 用的是同一段（SQL 文件之间不能互相引用，改规则两处一起改）。
--
-- 规则：某词在这个方向上**最近一次答错**之后，不看提示答对不满 2 次，就在本里。
-- 最近一次答错之后的作答只可能是答对（再错就成了新的「最近一次答错」），所以
-- 「之后答对的次数」就是连续答对的次数。看了提示答对的不算（也不打断）。
-- 词被删了的连不上 word，不算。
--
-- 参数：:learner、:direction（meaning / reading）、:level（全部 / N5..N1）。
-- 每行：word、label（汉字【读音】意思）、wrong_at（最近一次答错的时间）。
WITH last_wrong AS (
  SELECT word, max(id) AS wid
  FROM word_attempt
  WHERE learner = :learner AND direction = :direction AND correct = 0
  GROUP BY word
)
SELECT w.id AS word,
       CASE WHEN coalesce(w.kanji, '') <> '' AND w.kanji <> w.kana
            THEN w.kanji || '【' || w.kana || '】' ELSE w.kana || ' ' END
       || trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5) ELSE coalesce(w.meaning, '') END) AS label,
       (SELECT at FROM word_attempt WHERE id = lw.wid) AS wrong_at
FROM last_wrong lw
JOIN word w ON w.id = lw.word
WHERE (SELECT count(*) FROM word_attempt a
        WHERE a.learner = :learner AND a.direction = :direction
          AND a.word = lw.word AND a.id > lw.wid
          AND a.correct = 1 AND a.hinted = 0) < 2
  AND (:level = '全部' OR w.meaning GLOB '[[]' || :level || ']*')
ORDER BY lw.wid DESC
