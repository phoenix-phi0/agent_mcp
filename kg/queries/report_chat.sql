-- 学情页一个学生的问老师记录（只读）：最近 40 条，旧的在前。老师的回答长，
-- 表里截到 120 个字。
SELECT CASE role WHEN 'teacher' THEN '老师' ELSE '学生' END AS chat_who,
       CASE WHEN length(content) > 120 THEN substr(content, 1, 120) || '…' ELSE content END AS chat_text,
       created AS chat_at
FROM (SELECT * FROM chat_message WHERE learner = :student ORDER BY id DESC LIMIT 40)
ORDER BY id
