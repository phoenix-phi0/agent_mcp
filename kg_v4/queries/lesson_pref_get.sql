SELECT learner, series_code FROM lesson_pref WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
