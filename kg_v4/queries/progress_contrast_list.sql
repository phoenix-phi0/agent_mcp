SELECT a_code, b_code FROM kg_contrast WHERE a_code IN (SELECT code FROM kg_point) AND b_code IN (SELECT code FROM kg_point) ORDER BY id ASC
