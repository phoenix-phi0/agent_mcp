SELECT COALESCE(MAX(id), 0) FROM report_summary WHERE student = :student
