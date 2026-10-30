UPDATE teacher_assist_material SET title = :title, kind = :kind, content = :content, status = 'saved', updated_at = :now WHERE id = CAST(:id AS INTEGER) AND teacher = :teacher
