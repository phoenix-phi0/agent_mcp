SELECT DISTINCT l.item_code AS item_code FROM lesson_item_link l JOIN lesson_text t ON t.code = l.lesson_code WHERE t.level = :level AND COALESCE(l.subject_id,1) = CAST(:subject_id AS INTEGER)
