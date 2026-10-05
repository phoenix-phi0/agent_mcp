-- 自由练（按等级、考点）抽下一道，只要题号。「全部」或空表示不限。
-- 按课练走 question_pick_lesson.sql，复习薄弱点走 question_pick_review.sql。
--
-- 一轮里每个知识点只出一题：这里的「知识点」是语法条目（question.item，
-- 如 ようだ、ために），不是图上的大节点。:seen 是这一轮出过的题号
-- （「,a,b,」，quiz_state.round_seen），它们的条目这一轮不再出。挑不出来
-- （这个范围的条目都出过了）就不返回，调用方据此结束这一轮——候选条目不够
-- 一轮的题数时，一轮就是候选条目数。
--
-- 排序：这个人在这个条目上做得少的在前（「再来一轮」换到没出过、出得少的
-- 条目），同一条目里这道题做得少的在前；刚出过的那道（:last，上一轮最后
-- 一道）放后面；同一档里随机。
WITH done AS (
  SELECT DISTINCT item FROM question
  WHERE instr(coalesce(:seen, ''), ',' || code || ',') > 0
),
cnt AS (
  SELECT q.item, a.item AS code, count(*) AS n
  FROM attempt a JOIN question q ON q.code = a.item
  WHERE a.learner = :learner
  GROUP BY a.item
)
SELECT q.code
FROM question q
WHERE (:level IN ('', '全部') OR q.level = :level)
  AND (:kind IN ('', '全部') OR q.kind = :kind)
  AND q.item NOT IN (SELECT item FROM done)
ORDER BY
  coalesce((SELECT sum(n) FROM cnt WHERE cnt.item = q.item), 0),
  q.code = coalesce(:last, ''),
  coalesce((SELECT n FROM cnt WHERE cnt.code = q.code), 0),
  random()
LIMIT 1
