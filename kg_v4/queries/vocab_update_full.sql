UPDATE vocab_word SET kanji = :kanji, kana = :kana, meaning = :meaning, point_code = :point_code WHERE id = CAST(:word_id AS INTEGER)
