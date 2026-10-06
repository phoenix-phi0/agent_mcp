-- 改掌握标记。达标与否由 mastery_one（按掌握得分）算出来，这里只负责写。
-- updated 用本地时间，跟实体里「默认 现在」一致（datetime('now') 是 UTC）。
UPDATE mastery
SET mastered = CAST(:mastered AS INTEGER), updated = datetime('now','localtime')
WHERE learner = :learner AND point = :point
