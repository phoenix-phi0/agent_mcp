SELECT COALESCE(MAX(id), 0) FROM report_summary WHERE student = :student AND subject_id = CAST(:subject_id AS INTEGER)
