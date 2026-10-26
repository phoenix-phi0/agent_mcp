WITH RECURSIVE s(c) AS (SELECT :point_code UNION SELECT e.point_code FROM kg_edge e JOIN s ON e.pre_code = s.c) SELECT COUNT(*) FROM s WHERE c = :pre_code
