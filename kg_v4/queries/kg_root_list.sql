SELECT code, title FROM kg_point WHERE subject_id = CAST(:subject_id AS INTEGER) AND code NOT IN (SELECT point_code FROM kg_edge WHERE subject_id = CAST(:subject_id AS INTEGER)) ORDER BY id
