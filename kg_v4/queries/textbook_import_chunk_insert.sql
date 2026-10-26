INSERT INTO textbook_import_chunk (task_id, seq, title, content, status, retry_count) VALUES (CAST(:task_id AS INTEGER), CAST(:seq AS INTEGER), :title, :content, '待处理', 0)
