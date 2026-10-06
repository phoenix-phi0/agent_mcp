-- 「认证 核对」（routes/auth.zs）：多人模式下每个请求按 cookie 里的用户名查一次。
-- 查不到（停用了、删了）就当没登录；role 注入成 {current_role}，接口的「角色 teacher」看它
SELECT username, role, COALESCE(NULLIF(display_name, ''), username) AS label
FROM user
WHERE username = :username AND COALESCE(disabled, 0) = 0
