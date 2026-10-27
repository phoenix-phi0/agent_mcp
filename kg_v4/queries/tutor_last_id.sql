SELECT MAX(id) FROM tutor_message WHERE learner = :learner AND role = :role AND subject_id = CAST(:subject_id AS INTEGER)
