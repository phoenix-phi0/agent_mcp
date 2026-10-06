-- 「打开」传达到的那条问老师记录（浮层的「载入」，带着地址进来时用；从列表上点
-- 时整行已经拷进表单）：老师那条回复全文、学生前一句、这条回复上的传达摘录。
-- 只回学生的对话（:message_id 是老师那条）。
SELECT m.id AS message_id,
       coalesce((SELECT a.content FROM chat_message a
                 WHERE a.learner = m.learner AND a.role = 'learner' AND a.id < m.id
                 ORDER BY a.id DESC LIMIT 1), '') AS relay_msg_ask,
       m.content AS relay_msg_reply,
       coalesce((SELECT u.excerpt FROM relay_use u WHERE u.message_id = m.id ORDER BY u.id DESC LIMIT 1), '') AS relay_excerpt,
       m.created AS relay_at
FROM chat_message m
WHERE m.id = CAST(:message_id AS INTEGER) AND m.role = 'teacher'
