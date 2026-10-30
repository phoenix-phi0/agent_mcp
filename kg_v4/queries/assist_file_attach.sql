UPDATE teacher_assist_file SET attached = 1, last_used_at = :now WHERE id = CAST(:id AS INTEGER)
