-- 学情页一个学生的常错条目：按条目（题目挂的 item）数答错几次，前 10。
-- tally 是这个条目答对/答题，last_wrong 是最近一次答错的时间。只读。
SELECT i.code, i.label, coalesce(n.label, '') AS point_label,
       sum(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS wrong_n,
       sum(a.correct) || '/' || count(*) AS tally,
       max(CASE WHEN a.correct = 0 THEN a.at END) AS last_wrong
FROM attempt a
JOIN question q ON q.code = a.item
JOIN item i ON i.code = q.item
LEFT JOIN node n ON n.code = a.point
WHERE a.learner = :student
GROUP BY i.code
HAVING wrong_n > 0
ORDER BY wrong_n DESC, last_wrong DESC
LIMIT 10
