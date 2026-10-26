UPDATE account_login_fail SET fail_count = 0, locked_until = replace(datetime(replace(:now, '_', ' '), '+5 minutes'), ' ', '_') WHERE username = :username
