SELECT COUNT(*) AS n, COALESCE(SUM(correct), 0) AS r FROM (SELECT correct FROM progress_answer WHERE learner = :learner AND point_code = :point_code ORDER BY id DESC LIMIT 10)
