DELETE FROM lesson_point_link WHERE lesson_code IN (SELECT code FROM lesson_text WHERE series_code = :series_code)
