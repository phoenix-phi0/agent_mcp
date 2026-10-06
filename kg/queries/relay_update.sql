-- 改一条传达。只改得了这一页能改的（:student 空 = 全班的，不空 = 这个学生个人的），
-- 范围和启用状态不改。规整同 relay_insert（轮数空或 0 是 3）。先跑过 relay_check、relay_reset。
UPDATE teacher_relay
SET relay_point = trim(:relay_point),
    relay_urgency = :relay_urgency,
    relay_voice = :relay_voice,
    relay_facts = trim(coalesce(:relay_facts, '')),
    relay_keywords = trim(replace(replace(replace(replace(replace(replace(trim(coalesce(:relay_keywords, '')),
        '，', ','), '、', ','), '；', ','), ';', ','), '　', ','), ' ', ','), ','),
    relay_rounds = CAST(coalesce(nullif(nullif(trim(coalesce(:relay_rounds, '')), ''), '0'), '3') AS INTEGER),
    relay_due = trim(coalesce(:relay_due, '')),
    relay_by = :relay_by,
    relay_updated = datetime('now', 'localtime')
WHERE id = CAST(:relay_id AS INTEGER) AND coalesce(relay_student, '') = trim(coalesce(:student, ''))
