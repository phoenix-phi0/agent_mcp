WITH RECURSIVE
sp(rest_i, rest_v, sid, sver) AS (
  SELECT replace(COALESCE(setting_ids, ''), ' ', '') || ',', replace(COALESCE(setting_versions, ''), ' ', '') || ',', '', '' FROM teacher_rules_setting_use WHERE student = :student AND subject_id = CAST(:subj AS INTEGER)
  UNION ALL
  SELECT substr(rest_i, instr(rest_i, ',') + 1), substr(rest_v, instr(rest_v, ',') + 1), substr(rest_i, 1, instr(rest_i, ',') - 1), substr(rest_v, 1, instr(rest_v, ',') - 1) FROM sp WHERE rest_i <> ''
),
kw(sid, rest, word) AS (
  SELECT id, replace(COALESCE(keywords, ''), ' ', '') || ',', '' FROM teacher_rules_setting WHERE kind = 'card'
  UNION ALL
  SELECT sid, substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM kw WHERE rest <> ''
),
eff AS (
  SELECT s.id AS id, s.kind AS kind, s.content AS content, s.version AS version,
    CASE s.kind WHEN 'memory' THEN 0 WHEN 'note' THEN 1 ELSE 2 END AS k,
    CASE WHEN COALESCE(s.student, '') = '' THEN 0 ELSE 1 END AS g
  FROM teacher_rules_setting s
  WHERE s.enabled = 1
    AND (s.subject_id = CAST(:subj AS INTEGER) OR s.subject_id = 0)
    AND (COALESCE(s.student, '') = '' OR s.student = :student)
    AND s.kind IN ('memory', 'note', 'card')
    AND NOT (s.kind = 'note' AND s.once = 1 AND EXISTS (SELECT 1 FROM sp WHERE sp.sid = CAST(s.id AS TEXT) AND sp.sver = CAST(s.version AS TEXT)))
    AND (s.kind <> 'card' OR (:recent <> '' AND EXISTS (SELECT 1 FROM kw WHERE kw.sid = s.id AND kw.word <> '' AND instr(:recent, kw.word) > 0)))
)
SELECT
  COALESCE((SELECT group_concat(content, char(10)) FROM (SELECT content FROM eff WHERE kind = 'memory' ORDER BY g, id)), '') AS memory_text,
  COALESCE((SELECT group_concat(content, char(10)) FROM (SELECT content FROM eff WHERE kind = 'note' ORDER BY g, id)), '') AS note_text,
  COALESCE((SELECT group_concat(content, char(10)) FROM (SELECT content FROM eff WHERE kind = 'card' ORDER BY g, id)), '') AS card_text,
  COALESCE((SELECT group_concat(id, ',') FROM (SELECT id FROM eff ORDER BY k, g, id)), '') AS setting_ids,
  COALESCE((SELECT group_concat(version, ',') FROM (SELECT version FROM eff ORDER BY k, g, id)), '') AS setting_versions,
  (SELECT count(*) FROM eff) AS "count"
