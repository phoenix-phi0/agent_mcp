SELECT coalesce(sum(correct), 0) FROM answer WHERE learner = :learner AND point_id = CAST(:point_id AS INTEGER)
