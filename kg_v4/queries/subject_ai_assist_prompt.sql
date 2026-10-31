SELECT COALESCE(assist_prompt, '') AS assist_prompt FROM subject_ai WHERE subject_id = CAST(:subject_id AS INTEGER)
