-- 新建一条作答。
-- id 是自增主键，不在这里给。
INSERT INTO answer(learner, question, course, point, given, correct, seconds)
VALUES(:learner, :question, :course, :point, :given, CAST(:correct AS INTEGER), CAST(:seconds AS INTEGER))
