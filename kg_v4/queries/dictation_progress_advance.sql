UPDATE dictation_progress SET current_word_id = CAST(:word_id AS INTEGER), answered = 0, hinted = 0, asked_ids = :asked_ids, asked_count = asked_count + 1 WHERE learner = :learner
