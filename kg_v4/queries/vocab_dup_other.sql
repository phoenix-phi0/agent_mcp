SELECT id FROM vocab_word WHERE COALESCE(kanji,'') = :kanji AND kana = :kana AND id <> CAST(:word_id AS INTEGER) LIMIT 1
