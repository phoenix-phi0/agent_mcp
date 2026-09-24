-- 更新一条掌握度。learner 是表单字段。
UPDATE mastery SET
  node = :node,
  right_count = CAST(:right_count AS INTEGER),
  total = CAST(:total AS INTEGER),
  mastered = CAST(:mastered AS INTEGER)
WHERE learner = :learner
