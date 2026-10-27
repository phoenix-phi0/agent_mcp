SELECT id, student, summary, author, created_at FROM report_summary WHERE student = :student AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id DESC LIMIT 1
