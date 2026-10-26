SELECT code, name, intro, source, license, sort_order FROM lesson_series WHERE sort_order >= 0 ORDER BY sort_order ASC, id ASC
