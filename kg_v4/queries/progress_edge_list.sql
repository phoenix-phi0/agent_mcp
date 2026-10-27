SELECT pre_code, point_code FROM kg_edge WHERE subject_id = CAST(:subject_id AS INTEGER) ORDER BY id ASC
