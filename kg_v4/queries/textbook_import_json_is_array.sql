SELECT CASE WHEN json_valid(:examples) THEN (CASE WHEN json_type(:examples) = 'array' THEN 1 ELSE 0 END) ELSE 0 END
