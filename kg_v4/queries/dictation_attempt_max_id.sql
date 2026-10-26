SELECT COALESCE(MAX(id), 0) FROM dictation_attempt WHERE learner = :learner
