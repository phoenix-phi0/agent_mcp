UPDATE textbook_import_draft SET item_codes = NULLIF(:codes,'') WHERE id = CAST(:id AS INTEGER)
