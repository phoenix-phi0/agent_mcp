UPDATE textbook_import_draft SET point_codes = NULLIF(:codes,'') WHERE id = CAST(:id AS INTEGER)
