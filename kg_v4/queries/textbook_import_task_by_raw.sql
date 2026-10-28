SELECT id FROM textbook_import_task WHERE raw_text = :raw_text AND COALESCE(subject_id,1) = CAST(:subject_id AS INTEGER) ORDER BY id LIMIT 1
