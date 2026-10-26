INSERT INTO progress_mastery (learner, point_code, right_count, total_count, mastered, updated_at) VALUES (:learner, :point_code, CAST(:right_count AS INTEGER), CAST(:total_count AS INTEGER), 0, :at)
