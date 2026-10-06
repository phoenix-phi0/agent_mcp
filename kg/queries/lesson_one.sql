-- 读一课：教材页的阅读视图。没有这一课就查不到行。
--
-- head      抬头：《标题》 等级 第N课（课号）。课号末尾三位数就是「第N课」，
--           问老师时说「讲讲 N5 第46课」「讲一下 hb-n5-046」都认（lesson_ref.sql）
-- practice  做题页按这一课出题的地址；这一课没有题时是空串——界面上的
--           「练这一课」地址空就不画
-- quiz_note 没有题时的那句说明，有题时空串
-- ask/back  问老师页、回课文表的地址（界面名编过码）
-- explain   请老师讲解这一课：#问老师?lesson=…，问老师页「触发」teacher_send，
--           进去就发出讲解请求
SELECT l.code, l.level, l.title, l.summary,
       coalesce(l.formation, '') AS formation,
       l.explanation,
       n.qcount,
       '《' || l.title || '》　' || l.level || '　第' || CAST(substr(l.code, -3) AS INTEGER)
         || '课（' || l.code || '）' AS head,
       CASE WHEN n.qcount > 0 THEN '#%E5%81%9A%E9%A2%98?lesson=' || l.code ELSE '' END AS practice,
       CASE WHEN n.qcount > 0 THEN '这一课有 ' || n.qcount || ' 道题'
            ELSE '这一课还没有题，可以先问老师' END AS quiz_note,
       '#%E9%97%AE%E8%80%81%E5%B8%88' AS ask,
       '#%E9%97%AE%E8%80%81%E5%B8%88?lesson=' || l.code AS explain,
       '#%E6%95%99%E6%9D%90' AS back
FROM lesson l,
     (SELECT count(*) AS qcount FROM question WHERE lesson = :lesson) n
WHERE l.code = :lesson
