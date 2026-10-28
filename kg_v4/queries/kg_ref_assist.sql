SELECT COUNT(*) FROM teacher_assist_message WHERE point = :code AND subject_id = CAST(:subject_id AS INTEGER)
