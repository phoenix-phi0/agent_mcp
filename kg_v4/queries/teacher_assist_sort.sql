SELECT json_extract(value, '$.line') AS line FROM json_each(:j) ORDER BY CAST(json_extract(value, '$.score') AS REAL) ASC
