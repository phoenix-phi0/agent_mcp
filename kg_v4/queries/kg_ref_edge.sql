SELECT COUNT(*) FROM kg_edge WHERE (pre_code = :code OR point_code = :code) AND subject_id = CAST(:subject_id AS INTEGER)
