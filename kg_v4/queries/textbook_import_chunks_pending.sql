SELECT id FROM textbook_import_chunk WHERE task_id = CAST(:task_id AS INTEGER) AND status = '待处理' ORDER BY seq ASC, id ASC
