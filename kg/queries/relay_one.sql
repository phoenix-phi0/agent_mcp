-- 编辑传达浮层的「载入」：一条拉回表单。只拉这一页能改的（:student 空 = 全班的，
-- 不空 = 这个学生个人的），别的没有行。
SELECT r.id AS relay_id, r.relay_point, r.relay_urgency, r.relay_voice,
       coalesce(r.relay_facts, '') AS relay_facts, coalesce(r.relay_keywords, '') AS relay_keywords,
       r.relay_rounds, coalesce(r.relay_due, '') AS relay_due
FROM teacher_relay r
WHERE r.id = CAST(:relay_id AS INTEGER) AND coalesce(r.relay_student, '') = trim(coalesce(:student, ''))
