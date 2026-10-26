SELECT code, title FROM kg_point WHERE code NOT IN (SELECT point_code FROM kg_edge) ORDER BY id
