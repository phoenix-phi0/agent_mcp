-- AI 老师设定的列表。:student 空 = 「AI 老师设定」页：只列全班的；不空 = 学情里
-- 这个学生的页面：全班的（只读，标「全班」）和他个人的放在一起，全班的在前。
-- 种类按 记忆、作者注、关键词卡 排。
--
-- note_state  停用 / 启用 / 只用于下一条（个人的说用没用过；全班的在学生页上说
--             这个学生用没用过，在设定页上说已有几个学生用过）
-- mine        1 = 这一页能改（设定页上的全班、学生页上的个人），行上的按钮看它
-- note_content / note_once / student  不显示：行上点「编辑」时前端把整行拷进浮层
--             的表单（note_once 回 'true' / 'false'，开关认它）；student 跟地址
--             里的对上，就不用再调「载入」
WITH used AS (
  SELECT n.id, u.learner
  FROM teacher_note n JOIN chat_note_use u
    ON u.id > n.used_mark AND instr(',' || u.note_ids || ',', ',' || n.id || ',') > 0
  WHERE n.note_once = 1
)
SELECT n.id AS note_id, n.note_kind,
       CASE WHEN coalesce(n.note_student, '') = '' THEN '全班' ELSE '个人' END AS note_scope,
       coalesce(n.note_keywords, '') AS note_keywords,
       CASE WHEN length(n.note_content) > 60 THEN substr(n.note_content, 1, 60) || '…' ELSE n.note_content END AS note_brief,
       CASE WHEN n.note_enabled = 0 THEN '停用'
            WHEN n.note_once = 1 AND :student <> '' THEN
              CASE WHEN EXISTS (SELECT 1 FROM used WHERE used.id = n.id AND used.learner = :student)
                   THEN '只用于下一条·这个学生已用过' ELSE '只用于下一条·还没用' END
            WHEN n.note_once = 1 THEN
              '只用于下一条·已有 ' || (SELECT count(DISTINCT learner) FROM used WHERE used.id = n.id) || ' 个学生用过'
            ELSE '启用' END AS note_state,
       n.note_updated,
       coalesce(n.note_by, '') AS note_by,
       CASE WHEN coalesce(n.note_student, '') = :student THEN 1 ELSE 0 END AS mine,
       n.note_content,
       CASE WHEN n.note_once = 1 THEN 'true' ELSE 'false' END AS note_once,
       :student AS student
FROM teacher_note n
WHERE coalesce(n.note_student, '') = '' OR (:student <> '' AND n.note_student = :student)
ORDER BY CASE n.note_kind WHEN '记忆' THEN 1 WHEN '作者注' THEN 2 ELSE 3 END,
         CASE WHEN coalesce(n.note_student, '') = '' THEN 0 ELSE 1 END,
         n.id
