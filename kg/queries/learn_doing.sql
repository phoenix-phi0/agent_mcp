-- 在学但按当前达标线还没够的，带上差距——比只说「没掌握」有用。
--
-- 按传进来的线**现算**，不只看库里的 mastered 标记：那个标记是上次写入时
-- 按当时的线算的，而线是可调的（严格模式、考前冲刺）。只看标记的话，
-- 线提高之后，原本算掌握的那些既不在「可学」里也不在「在学」里，凭空
-- 消失——测试就是这么撞出来的。
--
-- 判定跟 mastery_one.sql 同一条规则：当前得分 ≥ :line 算掌握；已经掌握的
-- （mastered = 1）得分 ≥ :keep 就继续算。标记在这里只用来认「已经掌握过」，
-- 回落线要看它。
--
-- 标记仍然有用：解锁判断（learn_next）看它，那是每次出题都要做的事，
-- 不该每次重算全表。两者的取舍不同，所以用法也不同。
WITH cur AS (
  SELECT s.point, s.value FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(x.id) FROM score x
                 WHERE x.learner = s.learner AND x.point = s.point)
)
SELECT n.code, n.label, m.right, m.total,
       m.right * 100 / m.total AS rate,
       c.value AS score,
       CASE WHEN c.value IS NULL THEN '还没打分'
            ELSE '得分 ' || c.value || '，差 ' || (CAST(:line AS INTEGER) - c.value) || ' 分'
       END AS gap
FROM mastery m
JOIN node n ON n.code = m.point
LEFT JOIN cur c ON c.point = m.point
WHERE m.learner = :learner
  AND m.total > 0
  AND NOT coalesce(c.value >= CAST(:line AS INTEGER)
                   OR (m.mastered = 1 AND c.value >= CAST(:keep AS INTEGER)), 0)
ORDER BY m.updated DESC
LIMIT CAST(:limit AS INTEGER)
