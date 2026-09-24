-- 评分最高的文章，附打了几个分
--
-- 注意 CAST：参数从 DSL 传过来一律是字符串，而 SQLite 里
-- `count(...) >= '2'` 是文本跟数字比较，恒为假且不报错。
-- 聚合结果没有列亲和性，靠不了自动转换，只能在这里说清楚。
SELECT
  p.id,
  p.title,
  p.author,
  count(r.score)           AS 评分数,
  round(avg(r.score), 1)   AS 平均分
FROM post p
JOIN rating r ON r.post = p.id
GROUP BY p.id, p.title, p.author
HAVING count(r.score) >= CAST(:最少评分数 AS INTEGER)
ORDER BY 平均分 DESC
LIMIT CAST(:条数 AS INTEGER)
