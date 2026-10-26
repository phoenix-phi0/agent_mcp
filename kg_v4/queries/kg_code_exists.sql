SELECT (SELECT COUNT(*) FROM kg_item WHERE code = :code) + (SELECT COUNT(*) FROM kg_point WHERE code = :code)
