-- 停用 / 启用一个学生。只动 role = student 的：页面上停不了教师
UPDATE user SET disabled = CAST(:disabled AS INTEGER)
WHERE username = :username AND role = 'student'
