WITH RECURSIVE sp(rest, tok) AS (
  SELECT :studs || ',', ''
  UNION ALL
  SELECT substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM sp WHERE rest <> ''
)
SELECT DISTINCT tok AS username FROM sp WHERE tok <> '' ORDER BY tok
