UPDATE textbook_import_chunk SET status = '待处理', fail_reason = NULL, retry_count = retry_count + 1 WHERE id = CAST(:id AS INTEGER)
