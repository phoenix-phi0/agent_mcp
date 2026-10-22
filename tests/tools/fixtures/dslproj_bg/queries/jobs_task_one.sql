SELECT id, title, status, error FROM jobs_task WHERE id = CAST(:id AS INTEGER)
