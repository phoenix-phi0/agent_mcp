SELECT at FROM tutor_message WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id DESC LIMIT 1
