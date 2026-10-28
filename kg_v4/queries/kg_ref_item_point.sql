SELECT COUNT(*) FROM kg_item WHERE point_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
