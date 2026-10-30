SELECT id FROM teacher_assist_file WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND path = :path ORDER BY id DESC LIMIT 1
