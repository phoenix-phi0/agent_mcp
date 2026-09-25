-- 一个结构点下面的条目，按先后排。
--
-- after 指向同一个结构点下的前一个条目。用递归算出每个条目的序号：没有
-- after 的排 0，指向别人的排「那个 + 1」。同一层内按编号排，保证稳定。
WITH RECURSIVE ord(code, n) AS (
  SELECT code, 0 FROM item WHERE point = :point AND (after IS NULL OR after = '')
  UNION ALL
  SELECT i.code, ord.n + 1 FROM item i JOIN ord ON i.after = ord.code
  WHERE i.point = :point
)
SELECT i.code, i.label, COALESCE(MAX(o.n), 0) AS seq
FROM item i LEFT JOIN ord o ON o.code = i.code
WHERE i.point = :point
GROUP BY i.code, i.label
ORDER BY seq, i.code
