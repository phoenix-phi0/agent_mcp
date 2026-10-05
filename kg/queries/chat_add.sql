-- 记一条对话。内容空的插不进（NULLIF 撞非空约束），整个事务回滚。
-- links 是老师那条带的全部链接（chat_links 拼的 JSON 数组），没有就记 NULL；
-- link / link_text 照旧记一个（老数据只有这两列）。
INSERT INTO chat_message(learner, role, content, intent, lesson, link, link_text, links)
VALUES(:learner, :role, NULLIF(:content, ''), NULLIF(:intent, ''),
       NULLIF(:lesson, ''), NULLIF(:link, ''), NULLIF(:link_text, ''),
       NULLIF(NULLIF(:links, ''), '[]'))
