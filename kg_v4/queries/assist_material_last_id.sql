SELECT MAX(id) FROM teacher_assist_material WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER)
