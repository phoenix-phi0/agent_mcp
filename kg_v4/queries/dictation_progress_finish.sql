UPDATE dictation_progress SET current_word_id = 0, answered = 1 WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
