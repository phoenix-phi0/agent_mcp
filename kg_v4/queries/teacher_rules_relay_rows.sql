SELECT r.id AS relay_id,
  CASE WHEN COALESCE(r.student, '') = '' THEN '全班' ELSE '个人' END AS relay_scope,
  CASE WHEN r.urgency = 'urgent' THEN '立即' WHEN r.urgency = 'low' THEN '顺便' ELSE '尽快' END AS relay_urgency,
  COALESCE(r.tone, '') AS relay_voice,
  CASE WHEN length(r.must_info) > 60 THEN substr(r.must_info, 1, 60) || '…' ELSE r.must_info END AS relay_brief,
  COALESCE(r.facts, '') AS relay_facts,
  COALESCE(r.deadline, '') AS relay_due,
  CASE WHEN :student <> '' THEN '' ELSE '已传达 ' || COALESCE(d.n, 0) || '/总 ' || CAST(:total AS INTEGER) || CASE WHEN COALESCE(r.deadline, '') <> '' AND r.deadline < :today AND COALESCE(d.n, 0) < CAST(:total AS INTEGER) THEN '，已过期 ' || (CAST(:total AS INTEGER) - COALESCE(d.n, 0)) ELSE '' END END AS relay_done,
  CASE WHEN :student = '' THEN CASE WHEN r.enabled = 1 THEN '启用' ELSE '停用' END ELSE (CASE WHEN r.enabled = 0 THEN '停用·' ELSE '' END) || CASE WHEN st.id IS NOT NULL AND st.confirmed = 1 THEN '已传达（' || st.updated_at || '）' WHEN COALESCE(r.deadline, '') <> '' AND r.deadline < :today THEN '已过期（截止 ' || r.deadline || '，没传达到）' ELSE '待传达（已带入 ' || COALESCE(st.rounds_done, 0) || ' 轮）' || CASE WHEN st.finished = 1 THEN '·已带满' ELSE '' END END END AS relay_state_text,
  CASE WHEN r.enabled = 1 THEN '启用' ELSE '停用' END AS relay_enabled_text,
  '（暂不记录原话）' AS relay_excerpt,
  r.updated_at AS relay_updated,
  r.author AS relay_by,
  CASE WHEN COALESCE(r.student, '') = :student THEN 1 ELSE 0 END AS mine,
  r.must_info AS relay_point,
  COALESCE(r.keywords, '') AS relay_keywords,
  r.rounds AS relay_rounds,
  COALESCE(r.student, '') AS student,
  COALESCE(st.id, 0) AS message_id,
  CASE WHEN r.subject_id = 0 THEN '全部科目' ELSE :sname END AS relay_subject_label,
  CASE WHEN r.subject_id = 0 THEN '全部科目' ELSE '当前科目' END AS relay_subject_scope,
  CASE WHEN r.subject_id = 0 THEN CAST(:own AS INTEGER) ELSE CAST(:wr AS INTEGER) END AS can_edit
FROM teacher_rules_relay r
LEFT JOIN (SELECT relay_id, count(*) AS n FROM teacher_rules_relay_state WHERE confirmed = 1 AND instr(',' || :studs || ',', ',' || student || ',') > 0 GROUP BY relay_id) d ON d.relay_id = r.id
LEFT JOIN teacher_rules_relay_state st ON st.relay_id = r.id AND st.student = :student
WHERE (r.subject_id = CAST(:subj AS INTEGER) OR r.subject_id = 0) AND ((:student = '' AND COALESCE(r.student, '') = '') OR (:student <> '' AND (COALESCE(r.student, '') = '' OR r.student = :student)))
ORDER BY CASE WHEN COALESCE(r.student, '') = '' THEN 0 ELSE 1 END, r.id
