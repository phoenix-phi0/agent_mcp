SELECT id, code, name, kind, visibility, owner, status FROM subject_info WHERE id = CAST(:id AS INTEGER)
