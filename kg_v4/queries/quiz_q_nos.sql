SELECT question_no FROM quiz_question WHERE subject_id = CAST(:subject_id AS INTEGER) ORDER BY id
