-- 一个词属于哪个知识点，带上知识点的名称。
SELECT n.code, n.label
FROM word w JOIN node n ON n.code = w.point
WHERE w.id = CAST(:word_id AS INTEGER)
