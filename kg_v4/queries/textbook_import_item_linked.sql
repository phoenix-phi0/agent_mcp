SELECT DISTINCT item_code AS item_code FROM lesson_item_link WHERE COALESCE(subject_id,1) = CAST(:subject_id AS INTEGER)
