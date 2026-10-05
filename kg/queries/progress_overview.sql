-- 学习进度页的概览：掌握了几个知识点、一共答了几题、正确率。
--
-- empty=1 表示一道都没答过，界面上换成「还没有作答记录」那句。正确率是
-- 整数百分比（right*100/total 整除），没答过显示「—」。
--
-- review_link：答过题才有，复习薄弱点（#做题?mode=review）；没答过是空串，
-- 界面上的链接地址空就不画。
--
-- 平均得分：打过分的知识点各取当前分（最新一行，按 id）再平均，四舍五入
-- 成整数；一个都没打过分显示「—」。没打过分的点不算进去（不当 0 分）。
WITH a AS (
  SELECT count(*) AS n, coalesce(sum(correct), 0) AS r
  FROM attempt WHERE learner = :learner
),
sc AS (
  SELECT count(*) AS n, CAST(round(avg(1.0 * s.value)) AS INTEGER) AS avg
  FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
),
p AS (
  SELECT (SELECT count(*) FROM node) AS total,
         (SELECT count(*) FROM mastery
           WHERE learner = :learner AND mastered = 1) AS done
)
SELECT p.total, p.done, a.n AS answers, a.r AS right,
       CASE WHEN a.n > 0 THEN a.r * 100 / a.n ELSE 0 END AS rate,
       CASE WHEN a.n = 0 THEN 1 ELSE 0 END AS empty,
       '已掌握 ' || p.done || ' / 总知识点 ' || p.total AS head,
       '累计答题 ' || a.n AS answers_text,
       '正确率 ' || CASE WHEN a.n > 0 THEN (a.r * 100 / a.n) || '%' ELSE '—' END AS rate_text,
       sc.avg AS avg_score,
       '平均得分 ' || CASE WHEN sc.n > 0 THEN CAST(sc.avg AS TEXT) ELSE '—' END AS score_text,
       '#%E5%81%9A%E9%A2%98' AS quiz_link,
       CASE WHEN a.n > 0 THEN '#%E5%81%9A%E9%A2%98?mode=review' ELSE '' END AS review_link
FROM a, p, sc
