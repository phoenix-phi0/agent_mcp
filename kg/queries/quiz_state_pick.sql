-- 出了一道新题：记下筛选条件和当前题，清掉上一道的作答。
-- :reset 为 1（点「开始」）时这一轮的计数清零；「下一题」接着算。
INSERT INTO quiz_state(learner, pick_level, pick_kind, current, answered, right, total)
VALUES(:learner, :level, :kind, :code, 0, 0, 0)
ON CONFLICT(learner) DO UPDATE SET
  pick_level = :level,
  pick_kind = :kind,
  current = :code,
  answered = 0,
  choice = NULL,
  given = NULL,
  right = CASE WHEN CAST(:reset AS INTEGER) = 1 THEN 0 ELSE right END,
  total = CASE WHEN CAST(:reset AS INTEGER) = 1 THEN 0 ELSE total END
