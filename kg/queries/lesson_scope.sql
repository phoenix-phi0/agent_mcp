-- 按课文练习时顶栏那句说明，顺带这一课有几道题。没有这一课就查不到行。
SELECT l.code, l.level, l.title,
       (SELECT count(*) FROM question q WHERE q.lesson = l.code) AS n,
       '只练这一课：' || l.level || '《' || l.title || '》' AS scope
FROM lesson l
WHERE l.code = :lesson
