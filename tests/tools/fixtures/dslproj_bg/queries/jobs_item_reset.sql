UPDATE jobs_item SET status = '待处理', error = '' WHERE task_id = CAST(:task_id AS INTEGER) AND status = '失败'
