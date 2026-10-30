UPDATE teacher_assist_file SET last_used_at = :now WHERE id = CAST(:id AS INTEGER)
