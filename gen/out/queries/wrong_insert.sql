-- 新建一条错题本。
INSERT INTO wrong(learner, question, course, point, times)
VALUES(:learner, :question, :course, :point, CAST(:times AS INTEGER))
