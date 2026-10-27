SELECT id, code, name, point_code, after_form, prev_code FROM kg_item WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
