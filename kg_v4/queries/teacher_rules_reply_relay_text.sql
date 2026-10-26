WITH RECURSIVE u AS (
  SELECT relay_ids AS ids FROM teacher_rules_relay_use WHERE reply_id = CAST(:reply_id AS INTEGER) ORDER BY id DESC LIMIT 1
),
sp(n, rest, tok) AS (
  SELECT 0, replace(COALESCE((SELECT ids FROM u), ''), ' ', '') || ',', ''
  UNION ALL
  SELECT n + 1, substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM sp WHERE rest <> ''
)
SELECT COALESCE(group_concat(t, '、'), '') FROM (SELECT CASE WHEN r.id IS NULL THEN '已删传达#' || sp.tok ELSE '传达#' || sp.tok END AS t FROM sp LEFT JOIN teacher_rules_relay r ON CAST(r.id AS TEXT) = sp.tok WHERE sp.tok <> '' ORDER BY sp.n)
