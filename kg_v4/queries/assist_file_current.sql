SELECT * FROM teacher_assist_file WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND status = 'ok' AND attached = 1 ORDER BY id DESC LIMIT 1
