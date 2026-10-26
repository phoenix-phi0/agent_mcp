SELECT p.code AS code, p.title AS title FROM kg_edge e JOIN kg_point p ON p.code = e.point_code WHERE e.pre_code = :code ORDER BY p.id
