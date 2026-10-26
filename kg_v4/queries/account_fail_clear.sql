UPDATE account_login_fail SET fail_count = 0, locked_until = NULL WHERE username = :username
