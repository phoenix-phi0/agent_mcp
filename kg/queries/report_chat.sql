-- 学情页一个学生的问老师记录（只读）：最近 40 条，旧的在前。老师的回答长，
-- 表里截到 120 个字。
--
-- chat_notes：老师那条回答当时拼进提示词的 AI 老师设定（chat_note_use），写成
-- 「记忆#3、作者注#5」，按拼的顺序；设定后来删了的写「已删#id」。没用设定是空。
SELECT CASE m.role WHEN 'teacher' THEN '老师' ELSE '学生' END AS chat_who,
       CASE WHEN length(m.content) > 120 THEN substr(m.content, 1, 120) || '…' ELSE m.content END AS chat_text,
       m.created AS chat_at,
       coalesce((SELECT group_concat(coalesce(n.note_kind, '已删') || '#' || j.value, '、')
                 FROM chat_note_use u
                 JOIN json_each('[' || u.note_ids || ']') j
                 LEFT JOIN teacher_note n ON n.id = j.value
                 WHERE u.message_id = m.id), '') AS chat_notes
FROM (SELECT * FROM chat_message WHERE learner = :student ORDER BY id DESC LIMIT 40) m
ORDER BY m.id
