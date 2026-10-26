WITH RECURSIVE kw(sid, n, rest, word) AS (
  SELECT id, 0, replace(COALESCE(keywords, ''), ' ', '') || ',', '' FROM teacher_rules_setting WHERE kind = 'card'
  UNION ALL
  SELECT sid, n + 1, substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM kw WHERE rest <> ''
),
hit AS (
  SELECT sid, word, n FROM kw WHERE word <> '' AND :recent <> '' AND instr(:recent, word) > 0
)
SELECT s.id AS note_id,
  (SELECT h.word FROM hit h WHERE h.sid = s.id ORDER BY h.n LIMIT 1) AS hit_keyword,
  CASE WHEN length(s.content) > 60 THEN substr(s.content, 1, 60) || '…' ELSE s.content END AS note_brief,
  '放进去了' AS hit_placed
FROM teacher_rules_setting s
WHERE s.enabled = 1 AND s.kind = 'card' AND (COALESCE(s.student, '') = '' OR s.student = :student) AND EXISTS (SELECT 1 FROM hit h WHERE h.sid = s.id)
ORDER BY CASE WHEN COALESCE(s.student, '') = '' THEN 0 ELSE 1 END, s.id
