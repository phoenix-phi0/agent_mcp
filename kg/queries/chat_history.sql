-- 进「问老师」页面时把最近的对话放回消息流，字段就是消息流的消息：
-- who / text / kind，老师那条带 link / link_text 和 links。学习者那条跟前端
-- 回显的一样写「你」、kind=user，刷新前后看着一样。
--
-- links 是 JSON 文本（脚本里逐条「解析JSON」还原成列表）。老数据没有 links
-- 列的值，有 link 的拼成只有一个元素的数组，跟新数据一个样子。
SELECT CASE role WHEN 'teacher' THEN '老师' ELSE '你' END AS who,
       content AS text,
       CASE role WHEN 'teacher' THEN '' ELSE 'user' END AS kind,
       coalesce(link, '') AS link,
       coalesce(link_text, '') AS link_text,
       CASE WHEN links IS NOT NULL AND json_valid(links) THEN links
            WHEN coalesce(link, '') <> ''
            THEN json_array(json_object('href', link, 'text', coalesce(link_text, '')))
            ELSE '[]' END AS links
FROM (SELECT * FROM chat_message WHERE learner = :learner
      ORDER BY id DESC LIMIT 40)
ORDER BY id
