SELECT id, word_id, direction, answer FROM dictation_attempt WHERE learner = :learner AND id > CAST(:round_start AS INTEGER) AND correct = 0 ORDER BY id ASC
