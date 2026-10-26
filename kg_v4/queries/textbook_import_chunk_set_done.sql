UPDATE textbook_import_chunk SET status = '完成', fail_reason = NULL WHERE id = CAST(:id AS INTEGER)
