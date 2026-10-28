SELECT COUNT(*) FROM tutor_message WHERE learner = :learner AND role = 'user' AND subject_id = CAST(:subject_id AS INTEGER)
