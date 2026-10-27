SELECT item_code FROM lesson_item_link WHERE lesson_code = :lesson_code AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id ASC
