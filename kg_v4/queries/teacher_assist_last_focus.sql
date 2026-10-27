SELECT student, point FROM teacher_assist_message WHERE teacher = :teacher AND role = 'assistant' ORDER BY id DESC LIMIT 1
