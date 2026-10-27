SELECT COALESCE(MAX(id), 0) FROM dictation_attempt WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
