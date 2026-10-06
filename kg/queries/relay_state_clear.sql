-- 传达删掉以后，清掉它在各学生上的状态（relay_delete 之后跑）。
DELETE FROM relay_state
WHERE relay_id = CAST(:relay_id AS INTEGER)
  AND NOT EXISTS (SELECT 1 FROM teacher_relay r WHERE r.id = CAST(:relay_id AS INTEGER))
