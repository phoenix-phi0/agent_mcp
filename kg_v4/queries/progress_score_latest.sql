SELECT score FROM progress_score WHERE learner = :learner AND point_code = :point_code AND subject_id = CAST(:subject_id AS INTEGER) ORDER BY id DESC LIMIT 1
