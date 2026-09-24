-- 加一对「对照」（无向的易混对）。每对只存一次：小的放 a，大的放 b，
-- 所以 (i-adj, na-adj) 和 (na-adj, i-adj) 是同一行。
--
-- 对照不参与环检查——它不是依赖关系。平假名→片假名 是前置，
-- 片假名↔平假名 是对照，两种并存完全正常。
INSERT INTO contrast(a, b)
SELECT min(:x, :y), max(:x, :y)
WHERE :x <> :y
  AND EXISTS (SELECT 1 FROM node WHERE code = :x)
  AND EXISTS (SELECT 1 FROM node WHERE code = :y)
  AND NOT EXISTS (SELECT 1 FROM contrast
                  WHERE a = min(:x, :y) AND b = max(:x, :y))
