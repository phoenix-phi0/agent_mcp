SELECT id, student, summary, author, created_at FROM report_summary WHERE student = :student ORDER BY id DESC LIMIT 1
