SELECT COUNT(*) FROM progress_answer WHERE learner = :learner AND point_code = :point_code AND subject_id = CAST(:subject_id AS INTEGER)
