SELECT COALESCE(persona, '') AS persona FROM subject_ai WHERE subject_id = CAST(:subject_id AS INTEGER)
