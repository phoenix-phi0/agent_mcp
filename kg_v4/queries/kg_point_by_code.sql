SELECT id, code, title FROM kg_point WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
