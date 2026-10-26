WITH RECURSIVE u AS (
  SELECT setting_ids AS ids FROM teacher_rules_setting_use WHERE reply_id = CAST(:reply_id AS INTEGER) ORDER BY id DESC LIMIT 1
),
sp(n, rest, tok) AS (
  SELECT 0, replace(COALESCE((SELECT ids FROM u), ''), ' ', '') || ',', ''
  UNION ALL
  SELECT n + 1, substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM sp WHERE rest <> ''
)
SELECT COALESCE(group_concat(t, '、'), '') FROM (SELECT CASE WHEN s.id IS NULL THEN '已删#' || sp.tok ELSE (CASE s.kind WHEN 'memory' THEN '记忆' WHEN 'note' THEN '作者注' ELSE '关键词卡' END) || '#' || sp.tok END AS t FROM sp LEFT JOIN teacher_rules_setting s ON CAST(s.id AS TEXT) = sp.tok WHERE sp.tok <> '' ORDER BY sp.n)
