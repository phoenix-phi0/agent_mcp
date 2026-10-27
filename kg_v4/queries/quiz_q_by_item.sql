SELECT question_no, item_code FROM quiz_question WHERE item_code = :code AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id
