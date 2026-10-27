INSERT INTO progress_score (learner, point_code, score, at, subject_id) VALUES (:learner, :point_code, CAST(:score AS INTEGER), :at, CAST(:subject_id AS INTEGER))
