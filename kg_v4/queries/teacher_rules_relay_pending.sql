WITH p AS (
  SELECT r.id AS id, r.urgency AS urgency, COALESCE(r.tone, '') AS tone, r.must_info AS must_info, COALESCE(r.deadline, '') AS deadline, COALESCE(r.facts, '') AS facts, COALESCE(r.keywords, '') AS keywords, CASE r.urgency WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END AS u
  FROM teacher_rules_relay r
  WHERE r.enabled = 1
    AND (r.subject_id = CAST(:subj AS INTEGER) OR r.subject_id = 0)
    AND (COALESCE(r.student, '') = '' OR r.student = :student)
    AND (COALESCE(r.deadline, '') = '' OR r.deadline >= :today)
    AND NOT EXISTS (SELECT 1 FROM teacher_rules_relay_state s WHERE s.relay_id = r.id AND s.student = :student AND s.finished = 1)
)
SELECT
  COALESCE((SELECT group_concat(id, ',') FROM (SELECT id FROM p ORDER BY u, id)), '') AS relay_ids,
  COALESCE((SELECT group_concat(line, char(10)) FROM (SELECT '[传达#' || id || '] 紧急:' || (CASE urgency WHEN 'urgent' THEN '立即' WHEN 'low' THEN '顺便' ELSE '尽快' END) || ' 口吻:' || tone || ' 必须准确:' || must_info || (CASE WHEN facts <> '' THEN ' 原样说对:' || facts ELSE '' END) || (CASE WHEN keywords <> '' THEN ' 沾边提示:' || keywords ELSE '' END) || ' 截止:' || deadline AS line FROM p ORDER BY u, id)), '') AS prompt_text,
  (SELECT count(*) FROM p) AS "count"
