SELECT id, kind, COALESCE(student, '') AS student, COALESCE(keywords, '') AS keywords, content, enabled, once, version, author, updated_at FROM teacher_rules_setting WHERE id = CAST(:id AS INTEGER)
