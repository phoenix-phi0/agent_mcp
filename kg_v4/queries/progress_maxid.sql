SELECT COALESCE(MAX(id), 0) FROM progress_answer WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
