UPDATE account_user SET disabled = CAST(:disabled AS INTEGER) WHERE username = :username
