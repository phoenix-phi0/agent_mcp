-- 学情页一个学生的默写错词本：两个方向都列，规则同 dictation_book.sql（最近一次
-- 答错之后不看提示答对不满 2 次的还在本里）。只读。
WITH last_wrong AS (
  SELECT word, direction, max(id) AS wid
  FROM word_attempt
  WHERE learner = :student AND correct = 0
  GROUP BY word, direction
)
SELECT w.id AS word,
       CASE WHEN coalesce(w.kanji, '') <> '' AND w.kanji <> w.kana
            THEN w.kanji || '【' || w.kana || '】' ELSE w.kana || ' ' END
       || trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5) ELSE coalesce(w.meaning, '') END) AS label,
       CASE lw.direction WHEN 'meaning' THEN '看中文写日语' ELSE '看汉字写读音' END AS direction_label,
       (SELECT at FROM word_attempt WHERE id = lw.wid) AS last_wrong
FROM last_wrong lw
JOIN word w ON w.id = lw.word
WHERE (SELECT count(*) FROM word_attempt a
        WHERE a.learner = :student AND a.direction = lw.direction
          AND a.word = lw.word AND a.id > lw.wid
          AND a.correct = 1 AND a.hinted = 0) < 2
ORDER BY lw.wid DESC
