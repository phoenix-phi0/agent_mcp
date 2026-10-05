-- 记一次默写作答。只进不改。at 不填，用列默认值（本地时间）。
-- 不碰 attempt / mastery / score：默写不影响知识点得分。
INSERT INTO word_attempt(learner, word, direction, answer, correct, hinted)
VALUES(:learner, CAST(:word AS INTEGER), :direction, NULLIF(:answer, ''),
       CAST(:correct AS INTEGER), CAST(:hinted AS INTEGER))
