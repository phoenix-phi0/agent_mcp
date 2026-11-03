WITH RECURSIVE sp(student, rest_i, rest_v, sid, sver) AS (
  SELECT student, replace(COALESCE(setting_ids, ''), ' ', '') || ',', replace(COALESCE(setting_versions, ''), ' ', '') || ',', '', '' FROM teacher_rules_setting_use WHERE subject_id = CAST(:subj AS INTEGER)
  UNION ALL
  SELECT student, substr(rest_i, instr(rest_i, ',') + 1), substr(rest_v, instr(rest_v, ',') + 1), substr(rest_i, 1, instr(rest_i, ',') - 1), substr(rest_v, 1, instr(rest_v, ',') - 1) FROM sp WHERE rest_i <> ''
)
SELECT s.id AS note_id,
  CASE s.kind WHEN 'memory' THEN '记忆' WHEN 'note' THEN '作者注' ELSE '关键词卡' END AS note_kind,
  CASE WHEN COALESCE(s.student, '') = '' THEN '全班' ELSE '个人' END AS note_scope,
  COALESCE(s.keywords, '') AS note_keywords,
  CASE WHEN length(s.content) > 60 THEN substr(s.content, 1, 60) || '…' ELSE s.content END AS note_brief,
  CASE WHEN s.enabled = 0 THEN '停用'
    WHEN s.once = 1 AND :student <> '' THEN CASE WHEN EXISTS (SELECT 1 FROM sp WHERE sp.student = :student AND sp.sid = CAST(s.id AS TEXT) AND sp.sver = CAST(s.version AS TEXT)) THEN (CASE WHEN :lang = 'ja' THEN '次の返信のみ·この学生は使用済み' ELSE '只用于下一条·这个学生已用过' END) ELSE (CASE WHEN :lang = 'ja' THEN '次の返信のみ·未使用' ELSE '只用于下一条·还没用' END) END
    WHEN s.once = 1 THEN CASE WHEN :lang = 'ja' THEN '次の返信のみ·' || (SELECT count(DISTINCT sp.student) FROM sp WHERE sp.sid = CAST(s.id AS TEXT) AND sp.sver = CAST(s.version AS TEXT)) || '人の学生が使用済み' ELSE '只用于下一条·已有' || (SELECT count(DISTINCT sp.student) FROM sp WHERE sp.sid = CAST(s.id AS TEXT) AND sp.sver = CAST(s.version AS TEXT)) || '个学生用过' END
    ELSE '启用' END AS note_state,
  s.updated_at AS note_updated,
  s.author AS note_by,
  CASE WHEN COALESCE(s.student, '') = :student THEN 1 ELSE 0 END AS mine,
  s.content AS note_content,
  s.once AS note_once,
  COALESCE(s.student, '') AS student,
  CASE WHEN s.subject_id = 0 THEN '全部科目' ELSE :sname END AS note_subject_label,
  CASE WHEN s.subject_id = 0 THEN '全部科目' ELSE '当前科目' END AS note_subject_scope,
  CASE WHEN s.subject_id = 0 THEN CAST(:own AS INTEGER) ELSE CAST(:wr AS INTEGER) END AS can_edit
FROM teacher_rules_setting s
WHERE (s.subject_id = CAST(:subj AS INTEGER) OR s.subject_id = 0) AND ((:student = '' AND COALESCE(s.student, '') = '') OR (:student <> '' AND (COALESCE(s.student, '') = '' OR s.student = :student)))
ORDER BY CASE s.kind WHEN 'memory' THEN 0 WHEN 'note' THEN 1 ELSE 2 END, CASE WHEN COALESCE(s.student, '') = '' THEN 0 ELSE 1 END, s.id
