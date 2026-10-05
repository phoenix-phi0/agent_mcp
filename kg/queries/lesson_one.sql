-- 读一课：教材页的阅读视图。没有这一课就查不到行。
--
-- head      抬头：《标题》 等级
-- practice  做题页按这一课出题的地址；这一课没有题时是空串——界面上的
--           「练这一课」地址空就不画
-- quiz_note 没有题时的那句说明，有题时空串
-- ask/back  问老师页、回课文表的地址（界面名编过码）
SELECT l.code, l.level, l.title, l.summary,
       coalesce(l.formation, '') AS formation,
       l.explanation,
       n.qcount,
       '《' || l.title || '》　' || l.level AS head,
       CASE WHEN n.qcount > 0 THEN '#%E5%81%9A%E9%A2%98?lesson=' || l.code ELSE '' END AS practice,
       CASE WHEN n.qcount > 0 THEN '这一课有 ' || n.qcount || ' 道题'
            ELSE '这一课还没有题，可以先问老师' END AS quiz_note,
       '#%E9%97%AE%E8%80%81%E5%B8%88' AS ask,
       '#%E6%95%99%E6%9D%90' AS back
FROM lesson l,
     (SELECT count(*) AS qcount FROM question WHERE lesson = :lesson) n
WHERE l.code = :lesson
