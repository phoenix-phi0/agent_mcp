UPDATE lesson_pref SET series_code = :series_code WHERE learner = :learner AND subject_id = CAST(:subject_id AS INTEGER)
