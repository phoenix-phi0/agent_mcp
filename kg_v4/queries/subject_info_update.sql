UPDATE subject_info SET name = :name, intro = :intro, levels = :levels, updated_at = :now WHERE id = CAST(:id AS INTEGER)
