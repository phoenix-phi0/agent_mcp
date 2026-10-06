-- 编辑浮层的「载入」：一条设定拉回表单。只拉这一页能改的（:student 空 = 全班的，
-- 不空 = 这个学生个人的），别的没有行。「只用于下一条」回
-- 'true' / 'false'（前端的开关认它）。
SELECT n.id AS note_id, n.note_kind, coalesce(n.note_keywords, '') AS note_keywords,
       n.note_content,
       CASE WHEN n.note_once = 1 THEN 'true' ELSE 'false' END AS note_once
FROM teacher_note n
WHERE n.id = CAST(:note_id AS INTEGER) AND coalesce(n.note_student, '') = :student
