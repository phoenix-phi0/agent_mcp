SELECT MAX(id) FROM teacher_assist_draft WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER)
