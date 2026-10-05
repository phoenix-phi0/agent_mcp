-- 最近作答 20 条：时间、知识点（node.label）、条目（题目挂的条目名）、对错。
-- 按 id 倒序，不按 at：同一秒答的两题 at 一样。
SELECT a.at, coalesce(n.label, a.point) AS label,
       coalesce(i.label, '') AS item_label,
       CASE WHEN a.correct = 1 THEN '对' ELSE '错' END AS result
FROM attempt a
LEFT JOIN node n ON n.code = a.point
LEFT JOIN question q ON q.code = a.item
LEFT JOIN item i ON i.code = q.item
WHERE a.learner = :learner
ORDER BY a.id DESC
LIMIT 20
