-- 在学但按当前达标线还没够的，带上差距——比只说「没掌握」有用。
--
-- 按传进来的达标线**现算**，不看库里的 mastered 标记：那个标记是上次
-- 写入时按当时的线算的，而线是可调的（严格模式、考前冲刺）。看标记的话，
-- 线提高之后，原本算掌握的那些既不在「可学」里也不在「在学」里，凭空
-- 消失——测试就是这么撞出来的。
--
-- 标记仍然有用：解锁判断（learn_next）看它，那是每次出题都要做的事，
-- 不该每次重算全表。两者的取舍不同，所以用法也不同。
SELECT n.code, n.label, m.right, m.total,
       m.right * 100 / m.total AS rate,
       CASE WHEN m.total < CAST(:min_count AS INTEGER)
            THEN '还差 ' || (CAST(:min_count AS INTEGER) - m.total) || ' 题'
            ELSE '正确率差 '
                 || (CAST(:rate AS INTEGER) - m.right * 100 / m.total)
                 || ' 个点'
       END AS gap
FROM mastery m JOIN node n ON n.code = m.point
WHERE m.learner = :learner
  AND m.total > 0
  AND NOT (m.total >= CAST(:min_count AS INTEGER)
           AND m.right * 100 / m.total >= CAST(:rate AS INTEGER))
ORDER BY m.updated DESC
LIMIT CAST(:limit AS INTEGER)
