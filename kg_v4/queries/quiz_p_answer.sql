UPDATE quiz_progress SET answered = 1, right_count = CAST(:right_count AS INTEGER), last_correct = CAST(:last_correct AS INTEGER) WHERE learner = :learner
