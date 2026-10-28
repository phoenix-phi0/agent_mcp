SELECT COUNT(*) FROM progress_score WHERE point_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
