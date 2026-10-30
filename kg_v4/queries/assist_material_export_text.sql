SELECT title || char(10) || char(10) || content FROM teacher_assist_material WHERE id = CAST(:id AS INTEGER)
