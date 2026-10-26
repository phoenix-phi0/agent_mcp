SELECT id, kanji, kana, meaning, point_code FROM vocab_word WHERE COALESCE(kanji,'') = :kanji AND kana = :kana LIMIT 1
