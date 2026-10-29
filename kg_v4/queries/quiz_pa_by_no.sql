SELECT id FROM progress_answer WHERE question_no = :question_no AND subject_id = CAST(:subject_id AS INTEGER) LIMIT 1
