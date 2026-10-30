UPDATE teacher_assist_draft SET status = 'superseded' WHERE id = CAST(:id AS INTEGER) AND status = 'pending'
