UPDATE teacher_rules_relay SET enabled = CAST(:enabled AS INTEGER), updated_at = datetime('now', 'localtime') WHERE id = CAST(:id AS INTEGER)
