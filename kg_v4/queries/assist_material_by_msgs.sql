SELECT * FROM teacher_assist_material WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND source_msg_id IS NOT NULL ORDER BY id ASC
