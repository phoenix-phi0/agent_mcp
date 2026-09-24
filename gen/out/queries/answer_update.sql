-- 更新一条作答。id 从界面的 state 来（列表跳转时存进去的）。
UPDATE answer SET
  learner = :learner,
  question = :question,
  course = :course,
  point = :point,
  given = :given,
  correct = CAST(:correct AS INTEGER),
  seconds = CAST(:seconds AS INTEGER)
WHERE id = :id
