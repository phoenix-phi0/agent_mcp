-- 按主键查一条掌握度。
SELECT learner, node, right_count, total, mastered
FROM mastery
WHERE learner = :learner
