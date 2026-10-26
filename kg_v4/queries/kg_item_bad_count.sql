SELECT COUNT(*) FROM kg_item i WHERE i.point_code NOT IN (SELECT code FROM kg_point) OR (COALESCE(i.prev_code, '') <> '' AND i.prev_code NOT IN (SELECT code FROM kg_item))
