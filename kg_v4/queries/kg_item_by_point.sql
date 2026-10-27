SELECT code, name, point_code, after_form, prev_code FROM kg_item WHERE point_code = :point_code AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id
