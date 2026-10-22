UPDATE jobs_item SET status = '完成', result = :result, error = '' WHERE id = CAST(:id AS INTEGER)
