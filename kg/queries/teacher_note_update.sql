-- 改一条设定。只改得了这一页能改的（:student 空 = 全班的，不空 = 这个学生个人
-- 的），范围和启用状态不改（启用 / 停用走行上的按钮）。改过就重新算「只用于下一条」（used_mark 推到现在）。规整同
-- teacher_note_insert。先跑过 teacher_note_check。
UPDATE teacher_note
SET note_kind = :note_kind,
    note_keywords = trim(replace(replace(replace(replace(replace(replace(trim(coalesce(:note_keywords, '')),
        '，', ','), '、', ','), '；', ','), ';', ','), '　', ','), ' ', ','), ','),
    note_content = trim(:note_content),
    note_once = CASE WHEN :note_kind = '作者注' AND lower(coalesce(:note_once, '')) IN ('1', 'true', '是', 'on') THEN 1 ELSE 0 END,
    used_mark = (SELECT coalesce(max(id), 0) FROM chat_note_use),
    note_by = :note_by,
    note_updated = datetime('now', 'localtime')
WHERE id = CAST(:note_id AS INTEGER) AND coalesce(note_student, '') = trim(coalesce(:student, ''))
