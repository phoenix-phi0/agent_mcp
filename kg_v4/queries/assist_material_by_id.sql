SELECT * FROM teacher_assist_material WHERE id = CAST(:id AS INTEGER) AND teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER)
