INSERT INTO report_summary (student, summary, author, created_at, subject_id) VALUES (:student, :summary, :author, :created_at, CAST(:subject_id AS INTEGER))
