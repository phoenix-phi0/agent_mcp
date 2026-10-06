-- 这个学生在这条传达上「已带入」加一（第一次带入时建这一行，状态待传达）。跟
-- relay_use_add 同一个事务。
INSERT INTO relay_state(relay_id, learner, status, carried_n, state_updated)
VALUES(CAST(:relay_id AS INTEGER), :learner, '待传达', 1, datetime('now', 'localtime'))
ON CONFLICT(relay_id, learner) DO UPDATE
SET carried_n = carried_n + 1, state_updated = datetime('now', 'localtime')
