-- 教师建学生账号（「建用户」动词算好 password_hash 传进来）。role 固定 student：
-- 页面上建不出教师，教师只能用命令行 py -m kg 建教师。用户名唯一，重名插入失败
INSERT INTO user(username, password_hash, display_name, role, disabled)
VALUES(:username, :password_hash, NULLIF(:display_name, ''), 'student', 0)
