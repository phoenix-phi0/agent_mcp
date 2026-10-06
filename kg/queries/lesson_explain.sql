-- 请老师讲解一课：这一课的正文和这个学习者在这一课的答题情况。问老师用
-- （routes/teacher.zs）：教材页点「请老师讲解」（地址带 lesson）、原话里指名
-- 了某一课（lesson_ref.sql）时走这里。没有这一课就查不到行。
--
-- :lesson   课文编号
-- :learner  学习者
--
-- body     给模型看的课文正文，跟 lesson_find.sql 的 body 一个写法（标题、一句话、
--          接续、讲解、例句原文）
-- n        这一课的题数
-- link     做这一课的题（#做题?lesson=…），没有题时空串
-- read     教材页读这一课（#教材?lesson=…）
-- answers / rights  这个人做这一课的题答了几次、对了几次（做题页的作答，
--          attempt.item 是题号）
-- record   给模型看的答题情况：答过几次、对几次，答错过的条目和次数（多的在前，
--          最多 5 个），还没做过就写「还没做过这一课的题」
WITH q AS (
  SELECT code, item FROM question WHERE lesson = :lesson
),
a AS (
  SELECT at.correct, q.item
  FROM attempt at JOIN q ON q.code = at.item
  WHERE at.learner = :learner
),
wrong AS (
  SELECT coalesce(i.label, a.item) AS label, count(*) AS times
  FROM a LEFT JOIN item i ON i.code = a.item
  WHERE NOT a.correct
  GROUP BY a.item
  ORDER BY times DESC, label
  LIMIT 5
),
tally AS (
  SELECT count(*) AS answers, coalesce(sum(CASE WHEN correct THEN 1 ELSE 0 END), 0) AS rights FROM a
)
SELECT l.code, l.level, l.title, l.summary,
       (SELECT count(*) FROM q) AS n,
       CASE WHEN (SELECT count(*) FROM q) > 0 THEN '#%E5%81%9A%E9%A2%98?lesson=' || l.code ELSE '' END AS link,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS read,
       t.answers, t.rights,
       CASE WHEN t.answers = 0 THEN '还没做过这一课的题'
            ELSE '这一课的题答过 ' || t.answers || ' 次，答对 ' || t.rights || ' 次'
                 || coalesce('；答错过的条目：'
                    || (SELECT group_concat(label || '（' || times || ' 次）', '、') FROM wrong), '')
       END AS record,
       '《' || l.title || '》（' || l.level || '，课文 ' || l.code || '）' || char(10)
         || l.summary || char(10)
         || CASE WHEN coalesce(l.formation, '') <> '' THEN '接续：' || l.formation || char(10) ELSE '' END
         || l.explanation || char(10)
         || CASE WHEN coalesce(l.examples, '') <> '' THEN '例句：' || l.examples || char(10) ELSE '' END
         AS body
FROM lesson l, tally t
WHERE l.code = :lesson
