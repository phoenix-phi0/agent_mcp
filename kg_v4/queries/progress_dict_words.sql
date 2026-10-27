SELECT COUNT(DISTINCT word_id) FROM dictation_attempt WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
