-- 这一次判定的结果记在 relay_use 上：结论、AI 原话摘录、理由（判定失败时是出错原因）。
UPDATE relay_use
SET verdict = :verdict, excerpt = :quote, judge_note = :reason,
    judged_at = datetime('now', 'localtime')
WHERE id = CAST(:use_id AS INTEGER)
