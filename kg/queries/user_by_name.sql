-- 登录时按用户名取出哈希。「登录」「改密码」动词要的就是这两列，顺序不能换。
-- 停用的账号查不到：登录失败，跟密码错回同一句话
SELECT username, password_hash FROM user
WHERE username = :username AND COALESCE(disabled, 0) = 0
