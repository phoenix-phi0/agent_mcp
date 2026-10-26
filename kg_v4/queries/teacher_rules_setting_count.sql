SELECT count(*) FROM teacher_rules_setting WHERE (:kind = '' OR kind = :kind) AND (:student = '' OR COALESCE(student, '') = '' OR student = :student)
