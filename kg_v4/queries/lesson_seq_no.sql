SELECT CASE WHEN seq <> 0 THEN seq ELSE CAST(substr(code, -3) AS INTEGER) END AS nn FROM lesson_text WHERE code = :code
