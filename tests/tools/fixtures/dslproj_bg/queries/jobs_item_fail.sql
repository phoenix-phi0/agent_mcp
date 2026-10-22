UPDATE jobs_item SET status = '失败', error = :error WHERE id = CAST(:id AS INTEGER)
