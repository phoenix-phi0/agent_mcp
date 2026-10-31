SELECT COALESCE(caps,'') FROM subject_info WHERE id = CAST(:subject_id AS INTEGER)
