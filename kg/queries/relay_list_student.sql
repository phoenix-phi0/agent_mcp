-- 学情里一个学生的页面（#学情?student=xx）：对这个学生生效的传达——全班的（只读，
-- 标「全班」）和他个人的放在一起，全班的在前，再按 id。状态是这个学生在这条上的，
-- 写法同 relay_class_states。
--
-- mine  1 = 这一页能改（个人的），行上的按钮看它
-- 不显示的列：编辑时拷进浮层的全文（relay_point、relay_keywords、relay_rounds、
-- student），和「打开」那条问老师记录用的 message_id、relay_msg_ask、relay_msg_reply
SELECT r.id AS relay_id,
       CASE WHEN coalesce(r.relay_student, '') = '' THEN '全班' ELSE '个人' END AS relay_scope,
       r.relay_urgency, r.relay_voice,
       CASE WHEN length(r.relay_point) > 60 THEN substr(r.relay_point, 1, 60) || '…' ELSE r.relay_point END AS relay_brief,
       coalesce(r.relay_facts, '') AS relay_facts,
       coalesce(r.relay_due, '') AS relay_due,
       CASE WHEN r.relay_enabled = 0 THEN '停用·' ELSE '' END ||
       CASE WHEN s.status = '已传达' THEN '已传达（' || s.delivered_at || '）'
            WHEN s.status = '有误已停止' THEN '传达有误·已停止（更正那次还是说错，不再带入）'
            WHEN coalesce(r.relay_due, '') <> '' AND r.relay_due < date('now', 'localtime')
              THEN '已过期（截止 ' || r.relay_due || '，没传达到）'
            WHEN s.status = '传达有误' THEN '传达有误（下一条要求更正）'
            ELSE '待传达（已带入 ' || coalesce(s.carried_n, 0) || ' 轮）'
                 || CASE WHEN coalesce(s.miss_n, 0) >= r.relay_rounds
                           OR (coalesce(r.relay_due, '') <> '' AND r.relay_due <= date('now', 'localtime'))
                         THEN '·已升级为立即' ELSE '' END
       END AS relay_state_text,
       coalesce(s.excerpt, '') AS relay_excerpt,
       coalesce(s.delivered_at, '') AS relay_at,
       CASE WHEN r.relay_enabled = 1 THEN '启用' ELSE '停用' END AS relay_enabled_text,
       coalesce(r.relay_by, '') AS relay_by,
       CASE WHEN coalesce(r.relay_student, '') = :student THEN 1 ELSE 0 END AS mine,
       r.relay_point, coalesce(r.relay_keywords, '') AS relay_keywords, r.relay_rounds,
       :student AS student,
       s.message_id,
       coalesce((SELECT a.content FROM chat_message a
                 WHERE a.learner = :student AND a.role = 'learner' AND a.id < s.message_id
                 ORDER BY a.id DESC LIMIT 1), '') AS relay_msg_ask,
       coalesce(m.content, '') AS relay_msg_reply
FROM teacher_relay r
LEFT JOIN relay_state s ON s.relay_id = r.id AND s.learner = :student
LEFT JOIN chat_message m ON m.id = s.message_id
WHERE coalesce(r.relay_student, '') = '' OR r.relay_student = :student
ORDER BY CASE WHEN coalesce(r.relay_student, '') = '' THEN 0 ELSE 1 END, r.id
