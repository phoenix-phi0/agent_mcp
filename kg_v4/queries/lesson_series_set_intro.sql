UPDATE lesson_series SET intro = :intro WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
