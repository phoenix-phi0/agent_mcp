-- :code 的对照项（易混的另一方）。对照是无向的，每对只存一次，所以两个
-- 方向都要查。
SELECT n.code, n.label
FROM contrast c
JOIN node n ON n.code = CASE WHEN c.a = :code THEN c.b ELSE c.a END
WHERE c.a = :code OR c.b = :code
ORDER BY n.code
