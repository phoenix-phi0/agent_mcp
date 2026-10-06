-- 「AI老师设定」页：全班传达在每个学生上的状态（每个（要点，学生）一行），学生
-- 名单同 relay_list_class 的 roster。还没带入过的也列（待传达，已带入 0 轮）。
--
-- relay_state_text：
--   已传达（时间）
--   传达有误（下一条要求更正）/ 传达有误·已停止（更正那次还是说错，不再带入）
--   已过期（截止 …，没传达到）：过了截止日还没传达到，不再带入
--   待传达（已带入 n 轮），升级了的后面加「·已升级为立即」
--   传达停用了的前面加「停用·」
-- message_id、relay_msg_ask、relay_msg_reply：传达到（或说错）的那条老师回复和学生
-- 那句问话，行上「打开」浮层看（不显示的列）
WITH roster AS (
  SELECT x.learner
  FROM (SELECT username AS learner FROM user WHERE role = 'student'
        UNION SELECT DISTINCT learner FROM chat_message) x
  WHERE NOT EXISTS (SELECT 1 FROM user t WHERE t.username = x.learner AND t.role = 'teacher')
)
SELECT r.id AS relay_id,
       CASE WHEN length(r.relay_point) > 30 THEN substr(r.relay_point, 1, 30) || '…' ELSE r.relay_point END AS relay_brief,
       CASE WHEN coalesce(u.display_name, '') <> '' THEN u.display_name || '（' || ro.learner || '）'
            ELSE ro.learner END AS relay_student_label,
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
       s.message_id,
       coalesce((SELECT a.content FROM chat_message a
                 WHERE a.learner = ro.learner AND a.role = 'learner' AND a.id < s.message_id
                 ORDER BY a.id DESC LIMIT 1), '') AS relay_msg_ask,
       coalesce(m.content, '') AS relay_msg_reply
FROM teacher_relay r
CROSS JOIN roster ro
LEFT JOIN relay_state s ON s.relay_id = r.id AND s.learner = ro.learner
LEFT JOIN user u ON u.username = ro.learner
LEFT JOIN chat_message m ON m.id = s.message_id
WHERE coalesce(r.relay_student, '') = ''
ORDER BY r.id, ro.learner
