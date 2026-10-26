SELECT id FROM vocab_word WHERE COALESCE(kanji,'') = :kanji AND kana = :kana LIMIT 1
