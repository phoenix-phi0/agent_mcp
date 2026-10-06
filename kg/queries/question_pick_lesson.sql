-- 按课练时抽下一道：{code, other}，other = 1 是混进来的别的条目的题。
--
-- 一轮里每个知识点（语法条目 question.item）只出一题，而一课基本就是一个
-- 条目，所以一轮 = 本课 1 道 + 别的条目各 1 道（最多 :size - 1 个）：
--   第 1 道（:n = 0）  本课的题：这个人做得最少的那道（「再来一轮」就换到
--                     没出过的那道；本课的题都轮到过了再从头轮）
--   之后（:n >= 1）    别的条目的选择题，条目跟这一轮出过的都不同：先挑
--                     易混对比（contrast 表里跟本课条目成对的条目），
--                     没有了再挑同等级、跟本课选择题同考点的；同一档里这个人
--                     做得少的条目在前（再来一轮换一批对比条目）
-- 出够 :size 道、或者挑不出不同的条目了，就一道都不返回，调用方据此给
-- 「这一轮做完了」的卡（:n = 0 也挑不出就是这一课没有题）。
--
-- 为什么本课只出 1 道还要混别的：一课的题考的都是这一课的语法，挖空题的四个
-- 选项里往往只有正确那项是本课语法，学习者不看句子、挑本课那个词就能全对；
-- 混进易混的说法，本课语法就不总是答案了。
--
-- :seen 是这一轮出过的题号，「,a,b,」的样子；:n 是这一轮已经出了几道。
--
-- lq 是「课的题」：hanabira 的题库按课文编号打了标（question.lesson），照旧按
-- 标；别的系列的课没有自己的题，按映射取——挂着的条目（item_lesson）的题，
-- 加上直接挂的知识点（lesson_point）下所有条目的题。几个课文查询里是同一段。
-- hanabira 的课 lq 就是 question.lesson = 这一课，出题结果跟加系列之前一样。
WITH lq AS (
  SELECT q.lesson AS lesson, q.code, q.item FROM question q WHERE q.lesson IS NOT NULL
  UNION
  SELECT l.code, q.code, q.item FROM lesson l
  JOIN item_lesson il ON il.lesson = l.code JOIN question q ON q.item = il.item
  WHERE l.series <> 'hanabira'
  UNION
  SELECT l.code, q.code, q.item FROM lesson l
  JOIN lesson_point lp ON lp.lesson = l.code JOIN item i ON i.point = lp.point
  JOIN question q ON q.item = i.code
  WHERE l.series <> 'hanabira'
),
mine AS (
  SELECT DISTINCT item FROM lq WHERE lesson = :lesson
),
pair AS (
  SELECT b AS item FROM contrast WHERE a IN (SELECT item FROM mine)
  UNION
  SELECT a FROM contrast WHERE b IN (SELECT item FROM mine)
),
lv AS (
  SELECT level FROM lesson WHERE code = :lesson
),
kinds AS (
  SELECT DISTINCT kind FROM question
  WHERE code IN (SELECT code FROM lq WHERE lesson = :lesson) AND qtype = '选择'
),
done AS (
  SELECT DISTINCT item FROM question
  WHERE instr(coalesce(:seen, ''), ',' || code || ',') > 0
),
cnt AS (
  SELECT q.item, a.item AS code, count(*) AS n
  FROM attempt a JOIN question q ON q.code = a.item
  WHERE a.learner = :learner
  GROUP BY a.item
),
cand AS (
  SELECT q.code, q.item, 0 AS other, 0 AS tier
  FROM question q
  WHERE CAST(:n AS INTEGER) = 0 AND q.code IN (SELECT code FROM lq WHERE lesson = :lesson)
  UNION ALL
  SELECT q.code, q.item, 1 AS other,
         CASE WHEN q.item IN (SELECT item FROM pair) THEN 0 ELSE 1 END AS tier
  FROM question q
  WHERE CAST(:n AS INTEGER) BETWEEN 1 AND CAST(:size AS INTEGER) - 1
    AND q.qtype = '选择'
    AND q.item NOT IN (SELECT item FROM mine)
    AND q.item NOT IN (SELECT item FROM done)
    AND (q.item IN (SELECT item FROM pair)
         OR (q.level = (SELECT level FROM lv) AND q.kind IN (SELECT kind FROM kinds)))
)
SELECT c.code, c.other
FROM cand c
ORDER BY
  c.tier,
  CASE WHEN c.other = 1 THEN coalesce((SELECT sum(n) FROM cnt WHERE cnt.item = c.item), 0) ELSE 0 END,
  coalesce((SELECT n FROM cnt WHERE cnt.code = c.code), 0),
  c.code = coalesce(:last, ''),
  random()
LIMIT 1
