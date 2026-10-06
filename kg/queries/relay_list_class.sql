-- 「AI老师设定」页的全班传达列表。relay_done 是各学生的完成情况汇总「已传达 x/总 y」
-- （总数是全班学生：学生账号加上有问老师记录的学习者，教师除外，同
-- teacher_note_students），有说错的、过期的另外标出。
--
-- relay_state_text  启用 / 停用
-- 不显示的列：行上点「编辑」时前端把整行拷进浮层的表单（relay_point 等全文、
-- relay_rounds），student 跟地址对上，就不用再调「载入」
WITH roster AS (
  SELECT x.learner
  FROM (SELECT username AS learner FROM user WHERE role = 'student'
        UNION SELECT DISTINCT learner FROM chat_message) x
  WHERE NOT EXISTS (SELECT 1 FROM user t WHERE t.username = x.learner AND t.role = 'teacher')
),
tally AS (
  SELECT r.id,
         (SELECT count(*) FROM roster) AS total,
         (SELECT count(*) FROM relay_state s JOIN roster USING (learner)
          WHERE s.relay_id = r.id AND s.status = '已传达') AS done,
         (SELECT count(*) FROM relay_state s JOIN roster USING (learner)
          WHERE s.relay_id = r.id AND s.status IN ('传达有误', '有误已停止')) AS wrong
  FROM teacher_relay r
  WHERE coalesce(r.relay_student, '') = ''
)
SELECT r.id AS relay_id, r.relay_urgency, r.relay_voice,
       CASE WHEN length(r.relay_point) > 60 THEN substr(r.relay_point, 1, 60) || '…' ELSE r.relay_point END AS relay_brief,
       coalesce(r.relay_facts, '') AS relay_facts,
       coalesce(r.relay_due, '') AS relay_due,
       '已传达 ' || t.done || '/总 ' || t.total
         || CASE WHEN t.wrong > 0 THEN '，传达有误 ' || t.wrong ELSE '' END
         || CASE WHEN coalesce(r.relay_due, '') <> '' AND r.relay_due < date('now', 'localtime') AND t.done < t.total
                 THEN '，已过期 ' || (t.total - t.done - t.wrong) ELSE '' END AS relay_done,
       CASE WHEN r.relay_enabled = 1 THEN '启用' ELSE '停用' END AS relay_state_text,
       r.relay_updated, coalesce(r.relay_by, '') AS relay_by,
       r.relay_point, coalesce(r.relay_keywords, '') AS relay_keywords, r.relay_rounds,
       1 AS mine, '' AS student
FROM teacher_relay r JOIN tally t ON t.id = r.id
ORDER BY r.id
