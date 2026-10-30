SELECT * FROM teacher_assist_file WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND path = :path AND status = 'ok' ORDER BY id DESC LIMIT 1
