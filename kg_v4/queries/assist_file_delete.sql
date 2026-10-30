UPDATE teacher_assist_file SET status = 'deleted', attached = 0, "text" = '', stats = '' WHERE id = CAST(:id AS INTEGER)
