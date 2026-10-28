DELETE FROM kg_item WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
