INSERT INTO teacher_rules_relay_use (reply_id, student, relay_ids, at, subject_id) VALUES (CAST(:reply_id AS INTEGER), :student, :relay_ids, datetime('now', 'localtime'), CAST(:subj AS INTEGER))
