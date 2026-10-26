SELECT id, content FROM tutor_message WHERE learner = :learner AND role = 'teacher' AND summary_round = :round_key ORDER BY id DESC LIMIT 1
