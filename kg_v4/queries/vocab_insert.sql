INSERT INTO vocab_word (kanji, kana, meaning, point_code, subject_id) VALUES (:kanji, :kana, :meaning, :point_code, CAST(:subject_id AS INTEGER))
