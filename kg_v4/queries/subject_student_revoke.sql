UPDATE subject_student SET status = 'revoked' WHERE subject_id = CAST(:subject_id AS INTEGER) AND learner = :learner
