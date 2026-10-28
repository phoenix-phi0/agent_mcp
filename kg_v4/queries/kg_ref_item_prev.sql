SELECT COUNT(*) FROM kg_item WHERE prev_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
