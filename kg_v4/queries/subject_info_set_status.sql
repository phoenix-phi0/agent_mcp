UPDATE subject_info SET status = :status, updated_at = :now WHERE id = CAST(:id AS INTEGER)
