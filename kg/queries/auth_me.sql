-- /auth/me：显示名、角色、前端要藏的「侧」（JSON 数组）。学生藏「管理」，教师不藏
SELECT COALESCE(NULLIF(display_name, ''), username) AS label, role,
       CASE WHEN role = 'teacher' THEN '[]' ELSE '["管理"]' END AS hide
FROM user WHERE username = :username
