-- 行上的停用 / 启用：:enabled 1 启用、0 停用。重新启用时「只用于下一条」重新算
-- （used_mark 推到现在）。只动这一页能改的，同 teacher_note_update。
UPDATE teacher_note
SET note_enabled = CAST(:enabled AS INTEGER),
    used_mark = CASE WHEN CAST(:enabled AS INTEGER) = 1 AND note_enabled = 0
                     THEN (SELECT coalesce(max(id), 0) FROM chat_note_use) ELSE used_mark END,
    note_by = :note_by,
    note_updated = datetime('now', 'localtime')
WHERE id = CAST(:note_id AS INTEGER) AND coalesce(note_student, '') = trim(coalesce(:student, ''))
