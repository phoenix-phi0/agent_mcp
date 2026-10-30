UPDATE teacher_assist_draft SET status = :status, result = :result, error = :error, snapshot = :snapshot, claim = '' WHERE id = CAST(:id AS INTEGER) AND claim = :token
