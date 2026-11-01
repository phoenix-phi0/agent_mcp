SELECT id, username, password_hash, display_name, role, disabled, lang, created_at FROM account_user WHERE username = :username
