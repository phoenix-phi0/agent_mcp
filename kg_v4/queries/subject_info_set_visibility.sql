UPDATE subject_info SET visibility = :visibility, updated_at = :now WHERE id = CAST(:id AS INTEGER)
