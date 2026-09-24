-- 每个作者写了几篇、平均阅读数多少
SELECT
  a.code,
  a.name,
  a.level,
  count(p.id)                     AS 篇数,
  coalesce(round(avg(p.views)), 0) AS 平均阅读
FROM author a
LEFT JOIN post p ON p.author = a.code
GROUP BY a.code, a.name, a.level
ORDER BY 篇数 DESC
