UPDATE progress_mastery SET mastered = CAST(:mastered AS INTEGER), updated_at = :at WHERE learner = :learner AND point_code = :point_code AND subject_id = CAST(:subject_id AS INTEGER)
