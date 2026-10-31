SELECT COUNT(*) FROM lesson_text WHERE subject_id = CAST(:subject_id AS INTEGER) AND level = :level
