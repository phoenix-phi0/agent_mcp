UPDATE teacher_assist_file SET attached = 0 WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND attached = 1
