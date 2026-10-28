UPDATE subject_info SET name = :name, intro = :intro, updated_at = :now WHERE id = CAST(:id AS INTEGER)
