UPDATE subject_pref SET subject_id = CAST(:subject_id AS INTEGER) WHERE learner = :learner
