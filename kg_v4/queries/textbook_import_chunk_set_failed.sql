UPDATE textbook_import_chunk SET status = '失败', fail_reason = :fail_reason WHERE id = CAST(:id AS INTEGER)
