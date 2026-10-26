UPDATE textbook_import_chunk SET status = '处理中' WHERE id = CAST(:id AS INTEGER)
