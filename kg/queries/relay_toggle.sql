-- 行上的停用 / 启用传达：:enabled 1 启用、0 停用。状态不动（停用期间不带入，启用后
-- 接着传达）。只动这一页能改的，同 relay_update。
UPDATE teacher_relay
SET relay_enabled = CAST(:enabled AS INTEGER),
    relay_by = :relay_by,
    relay_updated = datetime('now', 'localtime')
WHERE id = CAST(:relay_id AS INTEGER) AND coalesce(relay_student, '') = trim(coalesce(:student, ''))
