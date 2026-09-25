-- 记一次作答。只进不改。
INSERT INTO attempt(learner, point, item, correct, at)
VALUES(:learner, :point, :item, CAST(:correct AS INTEGER), datetime('now'))
