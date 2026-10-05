-- 学习进度页的「单词默写」：练过几个词（两个方向合起来，按词算）、正确率、
-- 错词本里几个（两个方向各算，同一个词两个方向都错算 2 个）。
-- 错词本规则同 dictation_book.sql。link 是默写页的错词复习（#默写?source=review），
-- 错词本空时给不带参数的 #默写。
WITH a AS (
  SELECT count(*) AS n, coalesce(sum(correct), 0) AS r, count(DISTINCT word) AS words
  FROM word_attempt WHERE learner = :learner
),
last_wrong AS (
  SELECT word, direction, max(id) AS wid
  FROM word_attempt
  WHERE learner = :learner AND correct = 0
  GROUP BY word, direction
),
book AS (
  SELECT count(*) AS n
  FROM last_wrong lw
  JOIN word w ON w.id = lw.word
  WHERE (SELECT count(*) FROM word_attempt x
          WHERE x.learner = :learner AND x.direction = lw.direction
            AND x.word = lw.word AND x.id > lw.wid
            AND x.correct = 1 AND x.hinted = 0) < 2
)
SELECT a.words, a.n AS answers, a.r AS right, book.n AS book,
       CASE WHEN a.n > 0 THEN a.r * 100 / a.n ELSE 0 END AS rate,
       '练过 ' || a.words || ' 个词，默写 ' || a.n || ' 次，正确率 '
       || CASE WHEN a.n > 0 THEN (a.r * 100 / a.n) || '%' ELSE '—' END
       || '，错词本 ' || book.n || ' 个' AS text,
       CASE WHEN book.n > 0 THEN '#%E9%BB%98%E5%86%99?source=review' ELSE '#%E9%BB%98%E5%86%99' END AS link,
       CASE WHEN book.n > 0 THEN '去练错词' ELSE '去默写' END AS link_text
FROM a, book
