-- 复习薄弱点（#做题?mode=review）抽下一道：{code, tier, point}。
-- 只从这个人作答过的东西里挑，三种来源混着出：
--
--   a  低分点    当前掌握得分 < :score_line 的点（得分越低越优先）的题
--   b  错题重做  这个人最近一次作答是答错的那道题本身
--   c  防遗忘    已掌握（当前分 >= :score_line，或 mastery 达标）、最近一次
--                作答在 :stale_days 天以前的点的题，少量混入
--   d  兜底      作答过的点的其他题（上面三样都挑不出来时）
--
-- 这一轮第 k 道（k = :n + 1）该出哪种：k 是 5 的倍数出 c，3 的倍数出 b，
-- 其余出 a；该出的那种没有就按 a、b、c、d 的顺序往下退。一轮 10 道大约是
-- a 5、b 3、c 2。
--
-- 同一个点里挑题：这个人做得少的在前（没做过的最前），这一轮出过的靠后。
-- 低分点之间：得分 + 这一轮已出过的次数 × :spread——最低的先出，出过几道
-- 后让给下一个低分点，不会一轮全是同一个点。
--
-- 硬一点的规矩（排序的第一档，挑得出别的就不违反，题太少时才放宽）：
--   同一道题至少隔 :gap 道再出（这一轮最后 :gap 道里出过的不出）；
--   同一个点不连出超过 2 道（最后两道是同一个点，这道就换个点）。
--
-- :seen 是这一轮出过的题号，按出题顺序「,a,b,」（quiz_state.round_seen）；
-- :n 是这一轮已出了几道；:last 是当前那道。
WITH RECURSIVE
sp(pos, code, rest) AS (
  SELECT 0, '', substr(coalesce(:seen, ''), 2)
  UNION ALL
  SELECT pos + 1, substr(rest, 1, instr(rest, ',') - 1), substr(rest, instr(rest, ',') + 1)
  FROM sp WHERE instr(rest, ',') > 0
),
shown AS (
  SELECT sp.pos, sp.code, i.point
  FROM sp
  JOIN question q ON q.code = sp.code
  JOIN item i ON i.code = q.item
  WHERE sp.pos > 0
),
top AS (
  SELECT coalesce(max(pos), 0) AS n FROM shown
),
-- 最后两道是同一个点：这一道不出它
run AS (
  SELECT a.point FROM shown a, shown b, top
  WHERE a.pos = top.n AND b.pos = top.n - 1 AND a.point = b.point
),
near AS (
  SELECT shown.code FROM shown, top WHERE shown.pos > top.n - CAST(:gap AS INTEGER)
),
cur AS (
  SELECT s.point, s.value
  FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
),
att AS (
  SELECT point, max(at) AS last_at FROM attempt
  WHERE learner = :learner GROUP BY point
),
qn AS (
  SELECT item, count(*) AS n FROM attempt
  WHERE learner = :learner AND item IS NOT NULL GROUP BY item
),
wrong AS (
  SELECT a.item, a.id
  FROM attempt a
  WHERE a.learner = :learner AND a.correct = 0
    AND a.id = (SELECT max(b.id) FROM attempt b
                 WHERE b.learner = a.learner AND b.item = a.item)
),
-- 每道题所属的点，和这一轮这个点出过几道
qp AS (
  SELECT q.code, i.point,
         (SELECT count(*) FROM shown s WHERE s.point = i.point) AS pin
  FROM question q JOIN item i ON i.code = q.item
),
cand AS (
  SELECT qp.code, qp.point, 'a' AS tier,
         cur.value + qp.pin * CAST(:spread AS INTEGER) AS ord
  FROM qp JOIN cur ON cur.point = qp.point
  WHERE cur.value < CAST(:score_line AS INTEGER)
  UNION ALL
  SELECT qp.code, qp.point, 'b', -wrong.id
  FROM qp JOIN wrong ON wrong.item = qp.code
  UNION ALL
  SELECT qp.code, qp.point, 'c', julianday(att.last_at) + qp.pin
  FROM qp JOIN att ON att.point = qp.point
  LEFT JOIN cur ON cur.point = qp.point
  WHERE (cur.value >= CAST(:score_line AS INTEGER)
         OR (cur.value IS NULL AND qp.point IN
             (SELECT point FROM mastery WHERE learner = :learner AND mastered = 1)))
    AND att.last_at <= datetime('now', 'localtime', '-' || CAST(:stale_days AS INTEGER) || ' days')
  UNION ALL
  SELECT qp.code, qp.point, 'd', qp.pin
  FROM qp JOIN att ON att.point = qp.point
),
want AS (
  SELECT CASE WHEN (CAST(:n AS INTEGER) + 1) % 5 = 0 THEN 'c'
              WHEN (CAST(:n AS INTEGER) + 1) % 3 = 0 THEN 'b'
              ELSE 'a' END AS t
)
SELECT c.code, c.tier, c.point
FROM cand c, want
ORDER BY
  (c.code = coalesce(:last, '') OR c.code IN (SELECT code FROM near)
   OR c.point IN (SELECT point FROM run)),
  c.tier <> want.t,
  c.tier,
  c.ord,
  coalesce((SELECT n FROM qn WHERE qn.item = c.code), 0),
  instr(coalesce(:seen, ''), ',' || c.code || ',') > 0,
  random()
LIMIT 1
