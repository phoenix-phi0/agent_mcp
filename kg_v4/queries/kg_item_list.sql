SELECT code, name, point_code, after_form, prev_code FROM kg_item WHERE subject_id = CAST(:subject_id AS INTEGER) ORDER BY id
