SELECT id FROM vocab_word WHERE subject_id = CAST(:subject_id AS INTEGER) AND COALESCE(kanji,'') = :kanji AND kana = :kana AND id <> CAST(:word_id AS INTEGER) LIMIT 1
