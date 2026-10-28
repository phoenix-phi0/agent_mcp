UPDATE subject_teacher SET role = :role WHERE subject_id = CAST(:subject_id AS INTEGER) AND teacher = :teacher
