-- /auth/me：显示名、角色、前端要藏的「侧」（JSON 数组）。学生藏「管理」，教师不藏。
-- role_label 跟界面的「端 教师」「端 学生」比（前端按它分端）；badge 是顶栏最前面
-- 的标识，教师是「教师端」，学生不显示
SELECT COALESCE(NULLIF(display_name, ''), username) AS label, role,
       CASE role WHEN 'teacher' THEN '教师' WHEN 'student' THEN '学生' ELSE role END AS role_label,
       CASE WHEN role = 'teacher' THEN '教师端' ELSE '' END AS badge,
       CASE WHEN role = 'teacher' THEN '[]' ELSE '["管理"]' END AS hide
FROM user WHERE username = :username
