UPDATE teacher_rules_relay_state SET confirmed = 1, finished = 1, updated_at = datetime('now', 'localtime') WHERE relay_id = CAST(:relay_id AS INTEGER) AND student = :student
