SELECT COUNT(*) FROM textbook_import_draft d WHERE d.level = :level AND d.task_id IN (SELECT id FROM textbook_import_task WHERE subject_id = CAST(:subject_id AS INTEGER))
