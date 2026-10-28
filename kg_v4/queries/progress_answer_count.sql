SELECT COUNT(*) FROM progress_answer WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
