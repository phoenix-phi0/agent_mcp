-- 学情页一个学生的问老师记录（只读）：最近 40 条，旧的在前。老师的回答长，
-- 表里截到 120 个字。
--
-- chat_notes：老师那条回答当时拼进提示词的 AI 老师设定（chat_note_use），写成
-- 「记忆#3、作者注#5」，按拼的顺序；设定后来删了的写「已删#id」。带了传达的接着写
-- 「传达#2（已传达）」（括号里是这条回复的判定：待判定 / 已传达 / 未传达 / 有误 /
-- 判定失败；传达删了的写「已删传达#2」）。都没有是空。
SELECT CASE m.role WHEN 'teacher' THEN '老师' ELSE '学生' END AS chat_who,
       CASE WHEN length(m.content) > 120 THEN substr(m.content, 1, 120) || '…' ELSE m.content END AS chat_text,
       m.created AS chat_at,
       coalesce((SELECT group_concat(coalesce(n.note_kind, '已删') || '#' || j.value, '、')
                 FROM chat_note_use u
                 JOIN json_each('[' || u.note_ids || ']') j
                 LEFT JOIN teacher_note n ON n.id = j.value
                 WHERE u.message_id = m.id), '')
       || coalesce((SELECT CASE WHEN EXISTS (SELECT 1 FROM chat_note_use u WHERE u.message_id = m.id) THEN '、' ELSE '' END
                           || group_concat(CASE WHEN r.id IS NULL THEN '已删' ELSE '' END || '传达#' || x.relay_id
                                           || '（' || x.verdict || '）', '、')
                    FROM relay_use x LEFT JOIN teacher_relay r ON r.id = x.relay_id
                    WHERE x.message_id = m.id), '') AS chat_notes
FROM (SELECT * FROM chat_message WHERE learner = :student ORDER BY id DESC LIMIT 40) m
ORDER BY m.id
