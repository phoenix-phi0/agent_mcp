DELETE FROM quiz_question WHERE question_no = :question_no AND subject_id = CAST(:subject_id AS INTEGER)
