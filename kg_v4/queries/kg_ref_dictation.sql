SELECT COUNT(*) FROM dictation_progress WHERE source = :code AND subject_id = CAST(:subject_id AS INTEGER)
