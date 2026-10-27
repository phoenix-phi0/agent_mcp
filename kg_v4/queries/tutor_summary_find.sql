SELECT id, content FROM tutor_message WHERE learner = :learner AND role = 'teacher' AND subject_id = CAST(:subject_id AS INTEGER) AND summary_round = :round_key ORDER BY id DESC LIMIT 1
