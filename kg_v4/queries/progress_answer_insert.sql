INSERT INTO progress_answer (learner, point_code, question_no, correct, answer, at) VALUES (:learner, :point_code, :question_no, CAST(:correct AS INTEGER), :answer, :at)
