UPDATE textbook_import_task SET status = '失败', fail_reason = :reason WHERE id = CAST(:id AS INTEGER)
