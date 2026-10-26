SELECT point_code, right_count, total_count, mastered FROM progress_mastery WHERE learner = :learner AND total_count > 0 ORDER BY updated_at DESC, id DESC LIMIT 50
