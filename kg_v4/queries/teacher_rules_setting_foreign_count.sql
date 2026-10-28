WITH RECURSIVE sp(rest, tok) AS (
  SELECT replace(:ids, ' ', '') || ',', ''
  UNION ALL
  SELECT substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM sp WHERE rest <> ''
)
SELECT count(*) FROM sp WHERE tok <> '' AND EXISTS (SELECT 1 FROM teacher_rules_setting s WHERE CAST(s.id AS TEXT) = sp.tok AND s.subject_id <> CAST(:subj AS INTEGER) AND s.subject_id <> 0)
