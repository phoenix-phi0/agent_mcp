UPDATE teacher_assist_material SET source_msg_id = CAST(:msg_id AS INTEGER) WHERE id = CAST(:id AS INTEGER) AND teacher = :teacher
