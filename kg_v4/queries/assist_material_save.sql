UPDATE teacher_assist_material SET status = 'saved', updated_at = :now WHERE id = CAST(:id AS INTEGER) AND teacher = :teacher AND status = 'draft'
