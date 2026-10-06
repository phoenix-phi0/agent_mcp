-- 学情页一个学生的最近作答 20 条：时间、知识点、题干摘要（前 40 个字）、学生
-- 写的 / 选的（attempt.answer）、对错。按 id 倒序。只读。
SELECT a.at, coalesce(n.label, a.point) AS point_label,
       CASE WHEN length(coalesce(q.stem, '')) > 40 THEN substr(q.stem, 1, 40) || '…'
            ELSE coalesce(q.stem, '') END AS stem_brief,
       coalesce(a.answer, '') AS given_text,
       CASE WHEN a.correct = 1 THEN '对' ELSE '错' END AS result
FROM attempt a
LEFT JOIN node n ON n.code = a.point
LEFT JOIN question q ON q.code = a.item
WHERE a.learner = :student
ORDER BY a.id DESC
LIMIT 20
