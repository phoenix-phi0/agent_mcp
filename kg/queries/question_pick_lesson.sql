-- 按课练时抽下一道：{code, other}，other = 1 是混进来的对比题。
--
-- 为什么要混：一课的题考的都是这一课的语法，挖空题的四个选项里往往只有
-- 正确那项是本课语法（247 道挖空题里 160 道是这样），学习者不看句子、
-- 挑本课那个词就能全对。每第三道（这一轮第 3、6、9…道）换成别的课的题，
-- 本课语法就不总是答案了：
--   先挑易混对比（contrast 表里跟本课条目成对的条目）的题，
--   没有就挑同等级、跟本课选择题同考点的题。
-- 对比题只要选择题。本课和对比题大约二比一，这一轮本课的题每道都会出到一次
-- （:seen 里没有的才算候选）；本课的题都出过了就一道都不返回，调用方据此
-- 给「这一课做完一轮」的提示，不悄悄换到别的课。
--
-- :seen 是这一轮出过的题号，「,a,b,」的样子；:n 是这一轮已经出了几道。
WITH mine AS (
  SELECT DISTINCT item FROM question WHERE lesson = :lesson
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
  SELECT DISTINCT kind FROM question WHERE lesson = :lesson AND qtype = '选择'
),
left_n AS (
  SELECT count(*) AS n FROM question q
  WHERE q.lesson = :lesson AND instr(:seen, ',' || q.code || ',') = 0
),
cand AS (
  SELECT q.code, 0 AS other, 0 AS tier
  FROM question q
  WHERE q.lesson = :lesson AND instr(:seen, ',' || q.code || ',') = 0
  UNION ALL
  SELECT q.code, 1 AS other,
         CASE WHEN q.item IN (SELECT item FROM pair) THEN 0 ELSE 1 END AS tier
  FROM question q
  WHERE q.qtype = '选择'
    AND COALESCE(q.lesson, '') <> :lesson
    AND q.item NOT IN (SELECT item FROM mine)
    AND (q.item IN (SELECT item FROM pair)
         OR (q.level = (SELECT level FROM lv) AND q.kind IN (SELECT kind FROM kinds)))
)
SELECT c.code, c.other
FROM cand c, left_n
WHERE left_n.n > 0
ORDER BY
  -- 这一道该出对比题（第 3、6、9…道）就让对比题排前面，否则本课的排前面
  c.other <> ((CAST(:n AS INTEGER) + 1) % 3 = 0),
  c.tier,
  c.code = :last,
  instr(:seen, ',' || c.code || ',') > 0,
  EXISTS (SELECT 1 FROM attempt a WHERE a.learner = :learner AND a.item = c.code),
  random()
LIMIT 1
