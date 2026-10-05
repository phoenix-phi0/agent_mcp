-- 掌握度列表。带上 learner 供界面跳转用。
SELECT learner, node, right_count, total, mastered, updated
FROM mastery
ORDER BY learner DESC
LIMIT CAST(:limit AS INTEGER)
