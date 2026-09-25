-- 一个功能节点下面的条目，按先后排。
--
-- after 指向同一个功能下的前一个条目。用递归算序号：没有 after 的排 0，
-- 指向别人的排「那个 + 1」。同一层内按编号排，保证稳定。
--
-- 带上 form：条目接在哪个形式后面（辞书形、ない形、て形…）。功能决定
-- 什么时候用，形式决定怎么接——两样都要显示，学生才知道「表示义务用
-- なければならない，它接在ない形后面」。
WITH RECURSIVE ord(code, n) AS (
  SELECT code, 0 FROM item WHERE point = :point AND (after IS NULL OR after = '')
  UNION ALL
  SELECT i.code, ord.n + 1 FROM item i JOIN ord ON i.after = ord.code
  WHERE i.point = :point
)
SELECT i.code, i.label, COALESCE(f.label, '') AS form,
       COALESCE(MAX(o.n), 0) AS seq
FROM item i
LEFT JOIN ord o ON o.code = i.code
LEFT JOIN node f ON f.code = i.form
WHERE i.point = :point
GROUP BY i.code, i.label, f.label
ORDER BY seq, i.code
