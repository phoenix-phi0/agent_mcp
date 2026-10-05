-- 阅读数超过某个数的文章。用来演示数值比较为什么要 CAST。
--
-- views 是 INTEGER 列，SQLite 的列亲和性会把 '100' 自动转成 100，
-- 所以 `views > :min_views` 不加 CAST 也能工作。
--
-- 但别依赖这一点：一旦左边变成表达式（count(*)、sum(x)、a+b），
-- 亲和性就没了，比较退回纯值比较，文本永远大于数字——结果是恒真或
-- 恒假，而且不报错。加上 CAST 才是一致的写法。
SELECT id, title, views
FROM post
WHERE views > CAST(:min_views AS INTEGER)
ORDER BY views DESC
