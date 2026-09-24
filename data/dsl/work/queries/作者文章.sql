-- 某个作者的文章，按阅读数排
--
-- 作者是文本列，参数直接比就行。
-- 条数用在 LIMIT 上，要数字，所以 CAST——参数从 DSL 过来都是字符串。
SELECT id, title, views, published, created
FROM post
WHERE author = :作者
ORDER BY views DESC
LIMIT CAST(:条数 AS INTEGER)
