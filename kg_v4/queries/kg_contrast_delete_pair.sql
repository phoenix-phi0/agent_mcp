DELETE FROM kg_contrast WHERE a_code = :a_code AND b_code = :b_code AND subject_id = CAST(:subject_id AS INTEGER)
