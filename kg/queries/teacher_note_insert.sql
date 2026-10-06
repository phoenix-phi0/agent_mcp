-- 新建一条设定，建好就是启用的。:student 空 = 全班。关键词把全角逗号、顿号、分号、空白都规整成
-- 半角逗号；「只用于下一条」只对作者注有意义，别的种类存 0。used_mark 记成现在
-- 最大的使用记录 id：只算以后的使用。先跑过 teacher_note_check。
INSERT INTO teacher_note(note_kind, note_student, note_keywords, note_content,
                         note_enabled, note_once, used_mark, note_by, note_updated)
VALUES(:note_kind, trim(coalesce(:student, '')),
       trim(replace(replace(replace(replace(replace(replace(trim(coalesce(:note_keywords, '')),
            '，', ','), '、', ','), '；', ','), ';', ','), '　', ','), ' ', ','), ','),
       trim(:note_content),
       1,
       CASE WHEN :note_kind = '作者注' AND lower(coalesce(:note_once, '')) IN ('1', 'true', '是', 'on') THEN 1 ELSE 0 END,
       (SELECT coalesce(max(id), 0) FROM chat_note_use),
       :note_by, datetime('now', 'localtime'))
