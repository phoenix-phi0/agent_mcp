DELETE FROM subject_teacher WHERE subject_id = CAST(:subject_id AS INTEGER) AND teacher = :teacher
