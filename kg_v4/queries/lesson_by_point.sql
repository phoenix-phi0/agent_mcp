SELECT code, level, title, summary, series_code, seq FROM lesson_text WHERE code IN (SELECT lesson_code FROM lesson_point_link WHERE point_code = :point_code) ORDER BY seq ASC, id ASC
