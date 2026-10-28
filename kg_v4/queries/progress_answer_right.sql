SELECT COUNT(*) FROM progress_answer WHERE learner = :learner AND correct = 1 AND subject_id = CAST(:subject_id AS INTEGER)
