SELECT content, intent, at FROM tutor_message WHERE learner = :learner AND role = 'user' ORDER BY id DESC LIMIT 5
