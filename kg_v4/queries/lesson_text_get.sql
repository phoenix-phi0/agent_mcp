SELECT code, level, title, summary, explain, connection, examples, examples_edited, orig_title, series_code, seq FROM lesson_text WHERE code = :code AND subject_id = CAST(:subject_id AS INTEGER)
