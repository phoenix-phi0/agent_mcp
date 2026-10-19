SELECT count(*) FROM answer WHERE learner = :learner AND point_id = CAST(:point_id AS INTEGER)
