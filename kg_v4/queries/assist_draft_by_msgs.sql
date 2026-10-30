SELECT * FROM teacher_assist_draft WHERE teacher = :teacher AND subject_id = CAST(:subject_id AS INTEGER) AND INSTR(:ids, ',' || source_msg_id || ',') > 0 ORDER BY id ASC
