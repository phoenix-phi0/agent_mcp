INSERT INTO lesson_series (code, name, intro, source, license, sort_order) VALUES (:code, :name, :intro, :source, :license, CAST(:sort_order AS INTEGER))
