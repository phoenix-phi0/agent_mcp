SELECT id, task_id, seq, COALESCE(title,'') AS title, content, status, COALESCE(fail_reason,'') AS fail_reason, retry_count FROM textbook_import_chunk WHERE id = CAST(:id AS INTEGER)
