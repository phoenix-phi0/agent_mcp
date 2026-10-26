SELECT COALESCE(group_concat(word_id), '') FROM (SELECT DISTINCT word_id FROM dictation_attempt WHERE learner = :learner AND direction = :direction)
