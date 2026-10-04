-- 判题要的：题型、标准答案、可接受的写法，以及记学习记录要的结构点。
--
-- point 是条目所属的结构点：attempt / mastery 的 point 有外键指向 node，
-- 条目编号写不进去。具体哪道题另记在 attempt.item。
SELECT q.qtype, q.answer, COALESCE(q.accept, '') AS accept,
       q.item, i.point, n.label AS point_label
FROM question q
JOIN item i ON i.code = q.item
JOIN node n ON n.code = i.point
WHERE q.code = :code
