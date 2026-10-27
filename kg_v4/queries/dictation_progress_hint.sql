UPDATE dictation_progress SET hinted = 1 WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
