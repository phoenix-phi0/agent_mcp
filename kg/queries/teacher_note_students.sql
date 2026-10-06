-- 预览的「学生」下拉：账号里的学生，加上有问老师记录的学习者（单人模式下是 me），
-- 教师除外。[{value, label}]，label 是显示名（用户名）。
SELECT x.learner AS value,
       CASE WHEN coalesce(u.display_name, '') <> '' THEN u.display_name || '（' || x.learner || '）'
            ELSE x.learner END AS label
FROM (SELECT username AS learner FROM user WHERE role = 'student'
      UNION SELECT DISTINCT learner FROM chat_message) x
LEFT JOIN user u ON u.username = x.learner
WHERE NOT EXISTS (SELECT 1 FROM user t WHERE t.username = x.learner AND t.role = 'teacher')
ORDER BY x.learner
