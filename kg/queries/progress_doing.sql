-- 学习进度页的「在学」：答过的知识点都列出来，答对/答题和按当前达标线
-- 算的结论（达标 / 得分差几分 / 还没打分）。最近答过的在前。
--
-- 跟 learn_doing.sql 一样按传进来的线现算（规则见 mastery_one.sql：得分
-- ≥ :line 达标，已掌握的 ≥ :keep 继续算）；区别是这里达标的也留着，标
-- 「达标」——页面要看的是全貌。
WITH cur AS (
  SELECT s.point, s.value FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(x.id) FROM score x
                 WHERE x.learner = s.learner AND x.point = s.point)
)
SELECT n.code, n.label,
       m.right || '/' || m.total AS tally,
       CASE WHEN c.value IS NULL THEN '还没打分'
            WHEN c.value >= CAST(:line AS INTEGER)
              OR (m.mastered = 1 AND c.value >= CAST(:keep AS INTEGER))
            THEN '达标（得分 ' || c.value || '）'
            ELSE '得分 ' || c.value || '，差 ' || (CAST(:line AS INTEGER) - c.value) || ' 分'
       END AS verdict
FROM mastery m
JOIN node n ON n.code = m.point
LEFT JOIN cur c ON c.point = m.point
WHERE m.learner = :learner AND m.total > 0
ORDER BY m.updated DESC, m.id DESC
LIMIT 50
