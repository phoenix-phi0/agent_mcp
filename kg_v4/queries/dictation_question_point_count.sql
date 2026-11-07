SELECT COUNT(*) FROM dictation_question WHERE subject_id = CAST(:subject_id AS INTEGER) AND point_code = :source
