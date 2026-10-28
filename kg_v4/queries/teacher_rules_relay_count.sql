SELECT count(*) FROM teacher_rules_relay WHERE (subject_id = CAST(:subj AS INTEGER) OR subject_id = 0)
