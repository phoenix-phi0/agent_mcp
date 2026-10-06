-- 按课文练习时顶栏那句说明，顺带这一课有几道题、读这一课和课文表的地址
-- （一轮做完时给「回教材」「换一课」用），和请老师讲这一课的地址（#问老师?
-- lesson=…，问老师页进去就发出讲解请求）。没有这一课就查不到行。
--
-- 「本课《标题》+ 易混对比」：一轮是本课 1 道加别的条目各 1 道。有易混对比
-- （contrast 里跟本课条目成对）的课写「+ 易混对比」，没有的写「+ 同级对比」
-- ——混进来的题从哪儿来，跟 question_pick_lesson 一致。
SELECT l.code, l.level, l.title,
       (SELECT count(*) FROM question q WHERE q.lesson = l.code) AS n,
       '本课《' || l.title || '》'
       || CASE WHEN EXISTS (
                 SELECT 1 FROM contrast c
                 WHERE c.a IN (SELECT item FROM question WHERE lesson = l.code)
                    OR c.b IN (SELECT item FROM question WHERE lesson = l.code))
               THEN '+ 易混对比' ELSE '+ 同级对比' END AS scope,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS back,
       '#%E6%95%99%E6%9D%90' AS more,
       '#%E9%97%AE%E8%80%81%E5%B8%88?lesson=' || l.code AS explain
FROM lesson l
WHERE l.code = :lesson
