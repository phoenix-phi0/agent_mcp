-- 最近几轮对话拼成一段文字，给老师回答时当上下文。只取这个学习者的，
-- 最近 6 条（三来三回），每条截到 300 字，旧的在前。还没说过话就是空串。
-- 做题页请老师总结的那条（intent=总结）放宽到 800 字：学习者回到问老师页
-- 问「刚才那轮怎么样」时，总结里按知识点说的错因要接得上。
SELECT coalesce(group_concat(line, char(10)), '')
FROM (SELECT CASE role WHEN 'teacher' THEN '老师：' ELSE '学习者：' END
             || substr(content, 1, CASE WHEN intent = '总结' THEN 800 ELSE 300 END) AS line
      FROM (SELECT * FROM chat_message WHERE learner = :learner
            ORDER BY id DESC LIMIT 6)
      ORDER BY id)
