UPDATE lesson_series SET sort_order = -1 WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
