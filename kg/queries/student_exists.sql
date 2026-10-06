-- 这个用户名是不是学生：1 / 0。重置密码只重置学生的
SELECT count(*) FROM user WHERE username = :username AND role = 'student'
