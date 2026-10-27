UPDATE dictation_progress SET answered = 1, right_count = right_count + CAST(:correct AS INTEGER) WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
