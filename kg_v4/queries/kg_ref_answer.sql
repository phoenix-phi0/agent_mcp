SELECT COUNT(*) FROM progress_answer WHERE point_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
