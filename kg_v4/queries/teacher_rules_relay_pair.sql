SELECT r.id AS relay_id,
  CASE WHEN length(r.must_info) > 30 THEN substr(r.must_info, 1, 30) || '…' ELSE r.must_info END AS relay_brief,
  :label AS relay_student_label,
  CASE WHEN :lang = 'ja' THEN (CASE WHEN r.enabled = 0 THEN '無効·' ELSE '' END) || CASE WHEN st.id IS NOT NULL AND st.confirmed = 1 THEN '伝達済み（' || st.updated_at || '）' WHEN COALESCE(r.deadline, '') <> '' AND r.deadline < :today THEN '期限切れ（期限 ' || r.deadline || '、未伝達）' ELSE '未伝達（' || COALESCE(st.rounds_done, 0) || ' 回組み込み済み）' || CASE WHEN st.finished = 1 THEN '·上限到達' ELSE '' END END ELSE (CASE WHEN r.enabled = 0 THEN '停用·' ELSE '' END) || CASE WHEN st.id IS NOT NULL AND st.confirmed = 1 THEN '已传达（' || st.updated_at || '）' WHEN COALESCE(r.deadline, '') <> '' AND r.deadline < :today THEN '已过期（截止 ' || r.deadline || '，没传达到）' ELSE '待传达（已带入 ' || COALESCE(st.rounds_done, 0) || ' 轮）' || CASE WHEN st.finished = 1 THEN '·已带满' ELSE '' END END END AS relay_state_text,
  CASE WHEN :lang = 'ja' THEN '（原文は記録していません）' ELSE '（暂不记录原话）' END AS relay_excerpt,
  COALESCE(st.id, 0) AS message_id
FROM teacher_rules_relay r
LEFT JOIN teacher_rules_relay_state st ON st.relay_id = r.id AND st.student = :student
WHERE r.id = CAST(:relay_id AS INTEGER)
