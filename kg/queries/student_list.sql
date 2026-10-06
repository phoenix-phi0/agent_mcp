-- 学生管理页的列表：每个学生的作答数（做题 + 默写）和最近学习时间（作答、默写、
-- 问老师里最晚的一条）
SELECT u.username, COALESCE(u.display_name, '') AS display_name,
       CASE WHEN COALESCE(u.disabled, 0) = 1 THEN '已停用' ELSE '正常' END AS account_state,
       (SELECT count(*) FROM attempt a WHERE a.learner = u.username)
         + (SELECT count(*) FROM word_attempt w WHERE w.learner = u.username) AS attempt_n,
       COALESCE((SELECT max(t) FROM (
           SELECT max(at) AS t FROM attempt WHERE learner = u.username
           UNION ALL SELECT max(at) FROM word_attempt WHERE learner = u.username
           UNION ALL SELECT max(created) FROM chat_message WHERE learner = u.username)), '') AS last_active,
       u.created_at
FROM user u
WHERE u.role = 'student'
ORDER BY u.created_at DESC, u.username
