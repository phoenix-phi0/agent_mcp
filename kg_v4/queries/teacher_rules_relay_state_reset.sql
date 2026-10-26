UPDATE teacher_rules_relay_state SET rounds_done = 0, finished = 0, confirmed = 0, updated_at = datetime('now', 'localtime') WHERE relay_id = CAST(:relay_id AS INTEGER) AND student = :student
