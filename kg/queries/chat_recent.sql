-- 最近几轮对话拼成一段文字，给老师回答时当上下文。只取这个学习者的，
-- 最近 6 条（三来三回），每条截到 300 字，旧的在前。还没说过话就是空串。
SELECT coalesce(group_concat(line, char(10)), '')
FROM (SELECT CASE role WHEN 'teacher' THEN '老师：' ELSE '学习者：' END
             || substr(content, 1, 300) AS line
      FROM (SELECT * FROM chat_message WHERE learner = :learner
            ORDER BY id DESC LIMIT 6)
      ORDER BY id)
