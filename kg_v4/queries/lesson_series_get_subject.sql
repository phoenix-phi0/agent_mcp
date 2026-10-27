SELECT code, name, sort_order, subject_id FROM lesson_series WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
