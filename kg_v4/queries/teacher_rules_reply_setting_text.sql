WITH RECURSIVE u AS (
  SELECT setting_ids AS ids FROM teacher_rules_setting_use WHERE reply_id = CAST(:reply_id AS INTEGER) AND subject_id = CAST(:subj AS INTEGER) ORDER BY id DESC LIMIT 1
),
sp(n, rest, tok) AS (
  SELECT 0, replace(COALESCE((SELECT ids FROM u), ''), ' ', '') || ',', ''
  UNION ALL
  SELECT n + 1, substr(rest, instr(rest, ',') + 1), substr(rest, 1, instr(rest, ',') - 1) FROM sp WHERE rest <> ''
)
SELECT COALESCE(group_concat(t, '、'), '') FROM (SELECT CASE WHEN s.id IS NULL THEN (CASE WHEN :lang = 'ja' THEN '削除済み#' ELSE '已删#' END) || sp.tok ELSE (CASE s.kind WHEN 'memory' THEN (CASE WHEN :lang = 'ja' THEN '記憶' ELSE '记忆' END) WHEN 'note' THEN (CASE WHEN :lang = 'ja' THEN '作者メモ' ELSE '作者注' END) ELSE (CASE WHEN :lang = 'ja' THEN 'キーワードカード' ELSE '关键词卡' END) END) || '#' || sp.tok END AS t FROM sp LEFT JOIN teacher_rules_setting s ON CAST(s.id AS TEXT) = sp.tok AND (s.subject_id = CAST(:subj AS INTEGER) OR s.subject_id = 0) WHERE sp.tok <> '' ORDER BY sp.n)
