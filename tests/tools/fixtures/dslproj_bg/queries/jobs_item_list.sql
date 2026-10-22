SELECT id, body, result, status, error FROM jobs_item WHERE task_id = CAST(:task_id AS INTEGER) ORDER BY id
