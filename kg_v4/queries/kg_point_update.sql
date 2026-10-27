UPDATE kg_point SET title = :title WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
