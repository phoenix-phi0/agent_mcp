-- 这一轮答错的词：word_attempt 里这一轮起点（dictation_state.round_from）之后、
-- 这个人答错的，按作答顺序。label 是「汉字【读音】意思」，mine 是写的。
SELECT a.word,
       CASE WHEN coalesce(w.kanji, '') <> '' AND w.kanji <> w.kana
            THEN w.kanji || '【' || w.kana || '】' ELSE w.kana || ' ' END
       || trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5) ELSE coalesce(w.meaning, '') END) AS label,
       coalesce(a.answer, '') AS mine
FROM word_attempt a
JOIN dictation_state s ON s.learner = a.learner
JOIN word w ON w.id = a.word
WHERE a.learner = :learner AND a.id > s.round_from AND a.correct = 0
ORDER BY a.id
