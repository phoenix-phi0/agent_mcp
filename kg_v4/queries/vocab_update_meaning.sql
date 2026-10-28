UPDATE vocab_word SET meaning = :meaning, point_code = :point_code WHERE id = CAST(:word_id AS INTEGER) AND subject_id = CAST(:subject_id AS INTEGER)
