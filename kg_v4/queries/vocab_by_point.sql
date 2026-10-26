SELECT id, kanji, kana, meaning, point_code FROM vocab_word WHERE COALESCE(point_code,'') = :point_code ORDER BY id
