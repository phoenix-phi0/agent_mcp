-- 这个学习者最近 3 句话（不含这一句，这一句还没写进库），旧的在前，一句一行。
-- 关键词卡按它加上这一句判命中（scripts/teacher_notes.zs）。
SELECT coalesce(group_concat(content, char(10)), '')
FROM (SELECT content FROM (SELECT id, content FROM chat_message
                           WHERE learner = :learner AND role = 'learner'
                           ORDER BY id DESC LIMIT 3)
      ORDER BY id)
