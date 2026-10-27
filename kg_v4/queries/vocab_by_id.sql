SELECT id, kanji, kana, meaning, point_code FROM vocab_word WHERE id = CAST(:word_id AS INTEGER) AND subject_id = CAST(:subject_id AS INTEGER)
