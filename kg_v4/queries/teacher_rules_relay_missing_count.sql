WITH RECURSIVE sp(rest, tok) AS (
  SELECT replace(:ids, ' ', '') || ',', ''
  UNION ALL
  SELECT substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM sp WHERE rest <> ''
)
SELECT count(*) FROM sp WHERE tok <> '' AND NOT EXISTS (SELECT 1 FROM teacher_rules_relay r WHERE CAST(r.id AS TEXT) = sp.tok)
