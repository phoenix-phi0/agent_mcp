SELECT point_code, question_no, correct, COALESCE(answer, '') AS answer, at FROM progress_answer WHERE learner = :learner ORDER BY id DESC LIMIT CAST(:limit AS INTEGER)
