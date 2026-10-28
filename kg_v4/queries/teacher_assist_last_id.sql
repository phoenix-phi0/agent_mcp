SELECT MAX(id) FROM teacher_assist_message WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND role = 'assistant'
