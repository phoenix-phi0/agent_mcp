-- 学情页「全班薄弱点」的条目表：全班答错最多的条目（题目挂的 item）前 10。
-- 列同 report_weak_points，多一列所属知识点。只读。
SELECT i.code, i.label, coalesce(n.label, '') AS point_label,
       sum(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS wrong_n,
       count(*) AS answer_n,
       count(DISTINCT CASE WHEN a.correct = 0 THEN a.learner END) AS learner_n
FROM attempt a
JOIN question q ON q.code = a.item
JOIN item i ON i.code = q.item
LEFT JOIN node n ON n.code = a.point
WHERE NOT EXISTS (SELECT 1 FROM user t WHERE t.username = a.learner AND t.role = 'teacher')
GROUP BY i.code
HAVING wrong_n > 0
ORDER BY wrong_n DESC, answer_n DESC, i.code
LIMIT 10
