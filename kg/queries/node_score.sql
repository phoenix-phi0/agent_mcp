-- 知识图谱浮层「答对/答题」后面那一格：这个点的当前掌握得分（最新一行，
-- 按 id 取）。没打过分是空串，界面上那一格就不显示。总是出一行。
SELECT coalesce((SELECT CAST(s.value AS TEXT) FROM score s
                  WHERE s.learner = :learner AND s.point = :code
                  ORDER BY s.id DESC LIMIT 1), '') AS score
