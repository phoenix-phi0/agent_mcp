SELECT * FROM teacher_assist_file WHERE id = CAST(:file_id AS INTEGER) AND teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND status = 'ok'
