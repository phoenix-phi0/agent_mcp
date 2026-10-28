SELECT COUNT(*) FROM vocab_word WHERE point_code = :code AND subject_id = CAST(:subject_id AS INTEGER)
