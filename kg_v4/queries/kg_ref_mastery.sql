SELECT COUNT(*) FROM progress_mastery WHERE point_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
