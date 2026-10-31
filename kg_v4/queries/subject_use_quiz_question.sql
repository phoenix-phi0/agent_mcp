SELECT COUNT(*) FROM quiz_question WHERE subject_id = CAST(:subject_id AS INTEGER) AND level = :level
