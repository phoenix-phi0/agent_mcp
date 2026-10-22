SELECT id, body FROM jobs_item WHERE task_id = CAST(:task_id AS INTEGER) AND status = '待处理' ORDER BY id
