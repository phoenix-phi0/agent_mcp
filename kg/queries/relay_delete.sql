-- 删一条传达，只删得了这一页能改的。各学生的状态跟着删（relay_state_clear）；
-- relay_use 的历史留着（学情的问老师记录里显示成「已删#id」）。
DELETE FROM teacher_relay
WHERE id = CAST(:relay_id AS INTEGER) AND coalesce(relay_student, '') = trim(coalesce(:student, ''))
