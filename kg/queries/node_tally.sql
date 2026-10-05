-- 知识图谱浮层里那一行：这个点答对几道、答了几道。没做过（没有 mastery
-- 行或者答题数是 0）说「还没做过」。总是出一行。
SELECT CASE WHEN coalesce(m.total, 0) > 0
            THEN '答对 ' || m.right || ' / 答题 ' || m.total
                 || CASE WHEN m.mastered = 1 THEN '（已掌握）' ELSE '' END
            ELSE '还没做过' END AS tally
FROM node n
LEFT JOIN mastery m ON m.point = n.code AND m.learner = :learner
WHERE n.code = :code
