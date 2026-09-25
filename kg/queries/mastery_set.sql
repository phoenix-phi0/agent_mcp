-- 改掌握标记。达标与否由 mastery_one 算出来，这里只负责写。
UPDATE mastery
SET mastered = CAST(:mastered AS INTEGER), updated = datetime('now')
WHERE learner = :learner AND point = :point
