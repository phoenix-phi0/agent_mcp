-- 新建一条传达，建好就是启用的。:student 空 = 全班。关键词规整同 teacher_note_insert；
-- 轮数阈值空或 0 就是 3（新增的空表单里数字框是 0）。先跑过 relay_check。
INSERT INTO teacher_relay(relay_point, relay_student, relay_urgency, relay_voice, relay_facts,
                          relay_keywords, relay_rounds, relay_due, relay_enabled, relay_by,
                          relay_created, relay_updated)
VALUES(trim(:relay_point), trim(coalesce(:student, '')), :relay_urgency, :relay_voice,
       trim(coalesce(:relay_facts, '')),
       trim(replace(replace(replace(replace(replace(replace(trim(coalesce(:relay_keywords, '')),
            '，', ','), '、', ','), '；', ','), ';', ','), '　', ','), ' ', ','), ','),
       CAST(coalesce(nullif(nullif(trim(coalesce(:relay_rounds, '')), ''), '0'), '3') AS INTEGER),
       trim(coalesce(:relay_due, '')),
       1, :relay_by, datetime('now', 'localtime'), datetime('now', 'localtime'))
