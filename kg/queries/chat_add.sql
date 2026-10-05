-- 记一条对话。内容空的插不进（NULLIF 撞非空约束），整个事务回滚。
INSERT INTO chat_message(learner, role, content, intent, lesson, link, link_text)
VALUES(:learner, :role, NULLIF(:content, ''), NULLIF(:intent, ''),
       NULLIF(:lesson, ''), NULLIF(:link, ''), NULLIF(:link_text, ''))
