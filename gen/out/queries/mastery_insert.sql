-- 新建一条掌握度。
INSERT INTO mastery(learner, node, right_count, total, mastered)
VALUES(:learner, :node, CAST(:right_count AS INTEGER), CAST(:total AS INTEGER), CAST(:mastered AS INTEGER))
