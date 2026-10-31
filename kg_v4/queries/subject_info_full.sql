SELECT id, code, name, intro, kind, levels, visibility, owner, status FROM subject_info WHERE id = CAST(:id AS INTEGER)
