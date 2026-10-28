UPDATE subject_student SET status = 'active', assigned_by = :by WHERE subject_id = CAST(:subject_id AS INTEGER) AND learner = :learner
