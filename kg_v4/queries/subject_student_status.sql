SELECT status FROM subject_student WHERE subject_id = CAST(:subject_id AS INTEGER) AND learner = :learner
