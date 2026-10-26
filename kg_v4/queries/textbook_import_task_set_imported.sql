UPDATE textbook_import_task SET status = '已导入', report = :report WHERE id = CAST(:id AS INTEGER)
