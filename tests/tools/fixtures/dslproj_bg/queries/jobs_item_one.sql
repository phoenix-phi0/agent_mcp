SELECT id, body, status FROM jobs_item WHERE id = CAST(:id AS INTEGER)
