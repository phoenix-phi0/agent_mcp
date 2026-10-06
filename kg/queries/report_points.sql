-- 学情页一个学生的各知识点：答过题或打过分的点，答对/答题、当前得分、掌握没有。
-- 分低的在前（没打过分的排在最后）。只读。
WITH cur AS (
  SELECT s.point, s.value FROM score s
  WHERE s.learner = :student
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
),
pts AS (
  SELECT point FROM mastery WHERE learner = :student
  UNION SELECT point FROM cur
)
SELECT p.point AS code, n.label,
       coalesce(m.right, 0) || '/' || coalesce(m.total, 0) AS tally,
       coalesce(CAST(c.value AS TEXT), '—') AS score_text,
       CASE WHEN m.mastered = 1 THEN '已掌握' ELSE '' END AS mastered_text
FROM pts p
JOIN node n ON n.code = p.point
LEFT JOIN mastery m ON m.learner = :student AND m.point = p.point
LEFT JOIN cur c ON c.point = p.point
ORDER BY (c.value IS NULL), c.value, n.code
