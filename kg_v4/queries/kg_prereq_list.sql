SELECT p.code AS code, p.title AS title FROM kg_edge e JOIN kg_point p ON p.code = e.pre_code WHERE e.point_code = :code ORDER BY p.id
