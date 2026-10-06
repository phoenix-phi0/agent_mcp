-- 删一条设定。只删得了这一页能改的，同 teacher_note_update。chat_note_use 里
-- 用过它的记录留着（学情的问老师记录里显示成「已删#id」）。
DELETE FROM teacher_note
WHERE id = CAST(:note_id AS INTEGER) AND coalesce(note_student, '') = trim(coalesce(:student, ''))
