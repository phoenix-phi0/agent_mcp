SELECT a_code, b_code FROM kg_contrast WHERE subject_id = CAST(:subject_id AS INTEGER) AND (a_code = :code OR b_code = :code) ORDER BY id
