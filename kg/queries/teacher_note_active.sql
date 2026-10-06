-- 问老师拼提示词时，对这个学习者生效的教师设定（scripts/teacher_notes.zs 用）。
-- 启用的、全班的或者就是他的；「只用于下一条」的作者注他已经用过的不算
-- （chat_note_use 里他有一条 id > used_mark、note_ids 含这条的记录）。
--
-- 顺序：同一种类里全班的在前、个人的在后，再按 id。关键词卡的「命中顺序」就是
-- 这个顺序。scope_tag 是拼进提示词时每条前面的「（全班）/（只对这个学生）」；
-- size 是内容的字数，关键词卡算总字数上限用。
SELECT n.id, n.note_kind,
       CASE WHEN coalesce(n.note_student, '') = '' THEN '全班' ELSE '个人' END AS note_scope,
       coalesce(n.note_keywords, '') AS note_keywords,
       n.note_content,
       length(n.note_content) AS size,
       CASE WHEN coalesce(n.note_student, '') = '' THEN '（全班）' ELSE '（只对这个学生）' END AS scope_tag,
       CASE WHEN length(n.note_content) > 40 THEN substr(n.note_content, 1, 40) || '…' ELSE n.note_content END AS note_brief
FROM teacher_note n
WHERE n.note_enabled = 1
  AND (coalesce(n.note_student, '') = '' OR n.note_student = :learner)
  AND NOT (n.note_once = 1 AND EXISTS (
        SELECT 1 FROM chat_note_use u
        WHERE u.learner = :learner AND u.id > n.used_mark
          AND instr(',' || u.note_ids || ',', ',' || n.id || ',') > 0))
ORDER BY CASE n.note_kind WHEN '记忆' THEN 1 WHEN '作者注' THEN 2 ELSE 3 END,
         CASE WHEN coalesce(n.note_student, '') = '' THEN 0 ELSE 1 END,
         n.id
