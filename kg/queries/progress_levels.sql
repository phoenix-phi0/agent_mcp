-- 按等级的掌握情况，N5 到 N1 五行，没有题的等级也出一行（0/0）。
--
-- 知识点本身不分等级，这里按题目算：某等级的题挂在哪些条目上、条目属于
-- 哪些知识点，那些知识点就是这一级要掌握的（同一个点可能在几级都出现）。
--   tally    已掌握/总数
--   answers  答过的这一级的题数（attempt.item 是题号）
WITH lv(level, ord) AS (
  VALUES ('N5', 1), ('N4', 2), ('N3', 3), ('N2', 4), ('N1', 5)
),
pts AS (
  SELECT DISTINCT q.level, i.point
  FROM question q JOIN item i ON i.code = q.item
)
SELECT lv.level,
       (SELECT count(*) FROM pts p
         WHERE p.level = lv.level
           AND EXISTS (SELECT 1 FROM mastery m WHERE m.learner = :learner
                        AND m.point = p.point AND m.mastered = 1))
         || '/' || (SELECT count(*) FROM pts p WHERE p.level = lv.level) AS tally,
       (SELECT count(*) FROM attempt a JOIN question q ON q.code = a.item
         WHERE a.learner = :learner AND q.level = lv.level) AS answers
FROM lv
ORDER BY lv.ord
