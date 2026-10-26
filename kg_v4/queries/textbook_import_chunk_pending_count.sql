SELECT COUNT(*) FROM textbook_import_chunk WHERE task_id = CAST(:task_id AS INTEGER) AND status IN ('待处理','处理中')
