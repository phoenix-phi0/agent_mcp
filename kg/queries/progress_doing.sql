-- 学习进度页的「在学」：答过的知识点都列出来，答对/答题和按当前达标线
-- 算的结论（达标 / 还差几题 / 正确率差几个点）。最近答过的在前。
--
-- 跟 learn_doing.sql 一样按传进来的线现算，不看 mastered 标记（线是可调
-- 的）；区别是这里达标的也留着，标「达标」——页面要看的是全貌。
SELECT n.code, n.label,
       m.right || '/' || m.total AS tally,
       CASE WHEN m.total >= CAST(:min_count AS INTEGER)
             AND m.right * 100 / m.total >= CAST(:rate AS INTEGER) THEN '达标'
            WHEN m.total < CAST(:min_count AS INTEGER)
            THEN '还差 ' || (CAST(:min_count AS INTEGER) - m.total) || ' 题'
            ELSE '正确率差 ' || (CAST(:rate AS INTEGER) - m.right * 100 / m.total) || ' 个点'
       END AS verdict
FROM mastery m JOIN node n ON n.code = m.point
WHERE m.learner = :learner AND m.total > 0
ORDER BY m.updated DESC, m.id DESC
LIMIT 50
