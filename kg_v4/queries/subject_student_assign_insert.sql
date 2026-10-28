INSERT INTO subject_student (subject_id, learner, assigned_by, status, created_at) VALUES (CAST(:subject_id AS INTEGER), :learner, :by, 'active', :now)
