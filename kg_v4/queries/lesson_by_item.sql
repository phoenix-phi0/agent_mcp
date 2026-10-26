SELECT code, level, title, summary, series_code, seq FROM lesson_text WHERE code IN (SELECT lesson_code FROM lesson_item_link WHERE item_code = :item_code) ORDER BY seq ASC, id ASC
