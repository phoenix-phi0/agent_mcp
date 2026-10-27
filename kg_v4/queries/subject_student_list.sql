SELECT DISTINCT learner FROM subject_student WHERE subject_id = CAST(:subject_id AS INTEGER) AND status = 'active' ORDER BY learner
