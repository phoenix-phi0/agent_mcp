SELECT COUNT(*) FROM textbook_import_task WHERE series_code = :series_code AND status = '已撤下' AND COALESCE(subject_id,1) = CAST(:subject_id AS INTEGER)
