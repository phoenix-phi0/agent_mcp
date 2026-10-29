SELECT CASE WHEN :d <> '' AND julianday(:d) >= julianday(:now) - 7 THEN 1 ELSE 0 END
