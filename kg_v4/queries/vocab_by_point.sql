SELECT id, kanji, kana, meaning, point_code FROM vocab_word WHERE subject_id = CAST(:subject_id AS INTEGER) AND COALESCE(point_code,'') = :point_code ORDER BY id
