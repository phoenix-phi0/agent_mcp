-- 新增一篇文章
INSERT INTO post(author, title, body, views, published)
VALUES(:author, :title, :body, CAST(:views AS INTEGER), CAST(:published AS INTEGER))
