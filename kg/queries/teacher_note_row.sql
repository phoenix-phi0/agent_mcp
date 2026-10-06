-- 一条设定的原样（启用前再查一遍上限用），只查这一页能改的。
SELECT n.id AS note_id, n.note_kind, coalesce(n.note_keywords, '') AS note_keywords,
       n.note_content, n.note_enabled
FROM teacher_note n
WHERE n.id = CAST(:note_id AS INTEGER) AND coalesce(n.note_student, '') = trim(coalesce(:student, ''))
