SELECT CASE WHEN EXISTS (SELECT 1 FROM lesson_series WHERE code = :series_code) OR EXISTS (SELECT 1 FROM lesson_text WHERE series_code = :series_code) THEN 1 ELSE 0 END
