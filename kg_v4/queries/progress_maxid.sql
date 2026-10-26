SELECT COALESCE(MAX(id), 0) FROM progress_answer WHERE learner = :learner
