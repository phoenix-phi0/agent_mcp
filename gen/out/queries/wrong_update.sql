-- 更新一条错题本。learner 是表单字段。
UPDATE wrong SET
  question = :question,
  course = :course,
  point = :point,
  times = CAST(:times AS INTEGER)
WHERE learner = :learner
