SELECT COUNT(*) FROM progress_mastery WHERE learner = :learner AND mastered = 1 AND subject_id = CAST(:subject_id AS INTEGER)
