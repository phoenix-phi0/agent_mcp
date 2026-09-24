-- 从 :from 能不能走到 :to。返回 1 或 0。
-- 「学 :to 需不需要先会 :from」——直接的、隔几层的都算。
WITH RECURSIVE reach(n) AS (
  SELECT :from
  UNION
  SELECT p.dst FROM prereq p JOIN reach r ON p.src = r.n
)
SELECT CASE WHEN :from <> :to
             AND EXISTS (SELECT 1 FROM reach WHERE n = :to)
       THEN 1 ELSE 0 END AS reachable
