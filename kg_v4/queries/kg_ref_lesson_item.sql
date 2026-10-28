SELECT COUNT(*) FROM lesson_item_link WHERE item_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
