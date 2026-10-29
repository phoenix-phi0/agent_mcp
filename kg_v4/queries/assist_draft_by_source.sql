SELECT * FROM teacher_assist_draft WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND source_msg_id = CAST(:msg AS INTEGER) ORDER BY id DESC LIMIT 1
