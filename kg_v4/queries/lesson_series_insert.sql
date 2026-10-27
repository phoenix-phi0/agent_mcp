INSERT INTO lesson_series (code, name, intro, source, license, sort_order, subject_id) VALUES (:code, :name, :intro, :source, :license, CAST(:sort_order AS INTEGER), CAST(:subject_id AS INTEGER))
