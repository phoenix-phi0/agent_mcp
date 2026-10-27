SELECT question_no, item_code FROM quiz_question WHERE level = :level AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id
