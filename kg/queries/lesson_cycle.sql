-- 按课练一轮做完时：这一课的题是不是都轮到过了。{n, done}
--
-- 每轮的第 1 道是本课的题，挑的是这个人做得最少的那道（question_pick_lesson
-- .sql），所以本课的题是一道道轮着出的。这一轮那道本课题（:seen 的第一个）
-- 做过 k 次，本课每道题都至少做过 k 次，就是这一遍刚好轮完——done = 1，
-- 卡上说「这一课的 n 道题都出过了」，再来一轮从头再轮一遍。
-- 「做过」按 attempt 算（自由练、复习里碰到的本课题也算出过）。
WITH lead AS (
  SELECT substr(:seen, 2, instr(substr(:seen, 2), ',') - 1) AS code
),
cnt AS (
  SELECT q.code,
         (SELECT count(*) FROM attempt a WHERE a.learner = :learner AND a.item = q.code) AS k
  FROM question q WHERE q.lesson = :lesson
)
SELECT
  (SELECT count(*) FROM cnt) AS n,
  CASE WHEN (SELECT k FROM cnt WHERE code = (SELECT code FROM lead)) >= 1
        AND (SELECT min(k) FROM cnt) >= (SELECT k FROM cnt WHERE code = (SELECT code FROM lead))
       THEN 1 ELSE 0 END AS done
