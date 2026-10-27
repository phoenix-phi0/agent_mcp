SELECT s.subject_id FROM subject_student s JOIN subject_info i ON i.id = s.subject_id WHERE s.learner = :learner AND s.status = 'active' AND i.status = 'active' ORDER BY s.subject_id LIMIT 1
