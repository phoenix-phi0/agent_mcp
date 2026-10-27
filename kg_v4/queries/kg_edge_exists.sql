SELECT COUNT(*) FROM kg_edge WHERE pre_code = :pre_code AND point_code = :point_code AND subject_id = CAST(:subject_id AS INTEGER)
