-- 一个人在一个知识点上的现状，带上按掌握得分判出来的结论。
--
-- 掌握看得分，不看累计正确率：得分只算最近的作答、越近越重、分难易
-- （queries/score_calc.sql），累计正确率会被很久以前的作答拖住——开头
-- 错了十道、后面连对二十道，累计 66% 永远够不着 80%，后面的点就永远
-- 不解锁；反过来早期答得好、后来忘了的，累计还挂在线上。
--
-- 两条线（回落）：
--   :line  没掌握的，得分 ≥ 它才算掌握（默认 80）
--   :keep  已经掌握的，得分 ≥ 它就继续算（默认 60）
-- 只用一条线的话，80 分上下错一题对一题，标记就来回跳，下游刚解锁又锁上。
-- 掌握之后得分小幅回落交给「复习薄弱点」去补，不收回解锁。
--
-- :score 是刚算出来的当前分（scripts/score_update.zs 的 after）；空串表示
-- 这个点没法打分（没有作答），标记维持原样。
--
-- right / total / rate 只是给界面看的统计，不参与判断。
SELECT
  right,
  total,
  mastered,
  CASE WHEN total > 0 THEN right * 100 / total ELSE 0 END AS rate,
  CASE WHEN coalesce(:score, '') = '' THEN mastered
       WHEN CAST(:score AS INTEGER) >= CAST(:line AS INTEGER) THEN 1
       WHEN mastered = 1 AND CAST(:score AS INTEGER) >= CAST(:keep AS INTEGER) THEN 1
       ELSE 0 END AS ok
FROM mastery
WHERE learner = :learner AND point = :point
