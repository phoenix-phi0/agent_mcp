SELECT code, title FROM kg_point WHERE subject_id = CAST(:subject_id AS INTEGER) ORDER BY id
