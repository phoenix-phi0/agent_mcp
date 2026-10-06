-- 这个学习者现在待传达的要点，排好序（scripts/teacher_notes.zs 取第一条拼进提示词，
-- 一条回复最多带一条；预览也用它）。
--
-- 待传达：启用的、全班的或者就是他的；他这一条的状态是待传达或传达有误（已传达、
-- 有误已停止的不带）；没过截止日（截止日当天还带）。
--
-- urgency_now 是这次用的紧急程度：本来的 relay_urgency，下面几种升级为「立即」，
-- escalate 写明为什么（拼进提示词）：
--   传达有误           上次说错了，这次要更正
--   miss_n ≥ 轮数阈值  带了这么多轮还没传达到
--   今天是截止日
-- 排序：立即 > 尽快 > 顺便，同级按创建时间、id。queue_n 是排在后面的还有几条。
--
-- teacher_name：口吻「以老师名义」时用。relay_by 那个教师的显示名，不以「老师」
-- 结尾的补上「老师」（王 → 王老师）；没有账号、没有显示名（单人模式）就是「老师」。
-- fix_note：传达有误时上次判定的理由和说错的那句（要求更正用）。
WITH cand AS (
  SELECT r.id, r.relay_point, coalesce(r.relay_facts, '') AS relay_facts,
         coalesce(r.relay_keywords, '') AS relay_keywords,
         r.relay_urgency, r.relay_voice, r.relay_rounds,
         coalesce(r.relay_due, '') AS relay_due, r.relay_created,
         CASE WHEN coalesce(r.relay_student, '') = '' THEN '全班' ELSE '个人' END AS relay_scope,
         coalesce(s.status, '待传达') AS status,
         coalesce(s.carried_n, 0) AS carried_n,
         coalesce(s.miss_n, 0) AS miss_n,
         coalesce(s.excerpt, '') AS last_excerpt,
         CASE WHEN coalesce(u.display_name, '') = '' THEN '老师'
              WHEN u.display_name LIKE '%老师' THEN u.display_name
              ELSE u.display_name || '老师' END AS teacher_name,
         CASE WHEN coalesce(s.status, '') = '传达有误' THEN '上次转达时把必须准确的信息说错了，这次要更正'
              WHEN coalesce(s.miss_n, 0) >= r.relay_rounds THEN '已经带了 ' || s.miss_n || ' 轮还没说到'
              WHEN coalesce(r.relay_due, '') <> '' AND r.relay_due <= date('now', 'localtime') THEN '今天是截止日（' || r.relay_due || '）'
              ELSE '' END AS escalate,
         (SELECT coalesce(x.judge_note, '') FROM relay_use x
          WHERE x.relay_id = r.id AND x.learner = :learner AND x.verdict = '有误'
          ORDER BY x.id DESC LIMIT 1) AS fix_note
  FROM teacher_relay r
  LEFT JOIN relay_state s ON s.relay_id = r.id AND s.learner = :learner
  LEFT JOIN user u ON u.username = r.relay_by
  WHERE r.relay_enabled = 1
    AND (coalesce(r.relay_student, '') = '' OR r.relay_student = :learner)
    AND coalesce(s.status, '待传达') IN ('待传达', '传达有误')
    AND (coalesce(r.relay_due, '') = '' OR r.relay_due >= date('now', 'localtime'))
),
ranked AS (
  SELECT cand.*,
         CASE WHEN escalate <> '' THEN '立即' ELSE relay_urgency END AS urgency_now
  FROM cand
)
SELECT ranked.*,
       (SELECT count(*) FROM cand) - 1 AS queue_n,
       CASE WHEN length(relay_point) > 40 THEN substr(relay_point, 1, 40) || '…' ELSE relay_point END AS relay_brief
FROM ranked
ORDER BY CASE urgency_now WHEN '立即' THEN 1 WHEN '尽快' THEN 2 ELSE 3 END,
         relay_created, id
