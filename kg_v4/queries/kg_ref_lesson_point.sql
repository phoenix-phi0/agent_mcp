SELECT COUNT(*) FROM lesson_point_link WHERE point_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
