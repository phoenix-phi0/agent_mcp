SELECT right_count, total_count, mastered FROM progress_mastery WHERE learner = :learner AND point_code = :point_code AND subject_id = CAST(:subject_id AS INTEGER)
