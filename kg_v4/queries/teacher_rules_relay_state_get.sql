SELECT 1 AS ok, relay_id, student, confirmed, finished FROM teacher_rules_relay_state WHERE relay_id = CAST(:relay_id AS INTEGER) AND student = :student
