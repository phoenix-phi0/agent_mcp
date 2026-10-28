DELETE FROM kg_contrast WHERE (a_code = :code OR b_code = :code) AND subject_id = CAST(:subject_id AS INTEGER)
