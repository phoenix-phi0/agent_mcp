SELECT id, kanji, kana, meaning, point_code FROM vocab_word WHERE subject_id = CAST(:subject_id AS INTEGER) AND COALESCE(kanji,'') = :kanji AND kana = :kana LIMIT 1
