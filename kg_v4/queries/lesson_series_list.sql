SELECT code, name, intro, source, license, sort_order FROM lesson_series WHERE subject_id = CAST(:subject_id AS INTEGER) AND sort_order >= 0 ORDER BY sort_order ASC, id ASC
