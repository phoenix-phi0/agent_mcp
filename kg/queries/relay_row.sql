-- 一条传达在不在、能不能在这一页改（保存修改前查）。
SELECT r.id AS relay_id, r.relay_enabled
FROM teacher_relay r
WHERE r.id = CAST(:relay_id AS INTEGER) AND coalesce(r.relay_student, '') = trim(coalesce(:student, ''))
