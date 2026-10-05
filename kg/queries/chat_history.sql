-- 进「问老师」页面时把最近的对话放回消息流，字段就是消息流的消息：
-- who / text / kind，老师那条带 link / link_text。学习者那条跟前端回显的
-- 一样写「你」、kind=user，刷新前后看着一样。
SELECT CASE role WHEN 'teacher' THEN '老师' ELSE '你' END AS who,
       content AS text,
       CASE role WHEN 'teacher' THEN '' ELSE 'user' END AS kind,
       coalesce(link, '') AS link,
       coalesce(link_text, '') AS link_text
FROM (SELECT * FROM chat_message WHERE learner = :learner
      ORDER BY id DESC LIMIT 40)
ORDER BY id
