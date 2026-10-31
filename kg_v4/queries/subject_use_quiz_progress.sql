SELECT COUNT(*) FROM quiz_progress WHERE subject_id = CAST(:subject_id AS INTEGER) AND level = :level
