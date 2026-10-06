-- 改密码 / 重置密码：password_hash 由动词算好传进来
UPDATE user SET password_hash = :password_hash WHERE username = :username
