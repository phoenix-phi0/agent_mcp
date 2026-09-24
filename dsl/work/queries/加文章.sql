-- 新增一篇文章
INSERT INTO post(author, title, body, views, published)
VALUES(:作者, :标题, :正文, CAST(:阅读数 AS INTEGER), CAST(:已发布 AS INTEGER))
