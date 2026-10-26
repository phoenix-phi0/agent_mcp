SELECT COUNT(*) FROM textbook_import_draft WHERE task_id = CAST(:task_id AS INTEGER) AND status = :status
