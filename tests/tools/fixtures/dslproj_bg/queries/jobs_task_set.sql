UPDATE jobs_task SET status = :status, error = :error WHERE id = CAST(:id AS INTEGER)
