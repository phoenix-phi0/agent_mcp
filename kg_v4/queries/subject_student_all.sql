SELECT learner, status, assigned_by, created_at FROM subject_student WHERE subject_id = CAST(:subject_id AS INTEGER) ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, learner
