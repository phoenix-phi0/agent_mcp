-- 按课文练习时顶栏那句说明，顺带这一课有几道题、读这一课和课文表的地址
-- （一轮做完时给「回教材」「换一课」用）。没有这一课就查不到行。
--
-- 有易混对比（contrast 里跟本课条目成对）的课写「本课 + 易混对比」，没有
-- 的写「本课 + 同级对比题」——混进来的题从哪儿来，跟 question_pick_lesson
-- 一致。
SELECT l.code, l.level, l.title,
       (SELECT count(*) FROM question q WHERE q.lesson = l.code) AS n,
       '练这一课：' || l.level || '《' || l.title || '》'
       || CASE WHEN EXISTS (
                 SELECT 1 FROM contrast c
                 WHERE c.a IN (SELECT item FROM question WHERE lesson = l.code)
                    OR c.b IN (SELECT item FROM question WHERE lesson = l.code))
               THEN '（本课 + 易混对比）' ELSE '（本课 + 同级对比题）' END AS scope,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS back,
       '#%E6%95%99%E6%9D%90' AS more
FROM lesson l
WHERE l.code = :lesson
