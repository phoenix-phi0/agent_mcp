INSERT INTO subject_teacher (subject_id, teacher, role, created_at) VALUES (CAST(:subject_id AS INTEGER), :teacher, :role, :now)
