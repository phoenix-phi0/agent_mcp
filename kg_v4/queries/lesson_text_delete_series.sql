DELETE FROM lesson_text WHERE series_code = :series_code AND subject_id = CAST(:subject_id AS INTEGER)
