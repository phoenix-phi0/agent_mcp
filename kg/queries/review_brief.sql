-- 复习薄弱点的一句话依据：做题页顶栏的范围（「复习薄弱点：推量判断、授受…」）
-- 和问老师出题意图的回复（「推量判断 44、授受 51」）用。一行：
--
--   answers   这个人一共答过几题（0 = 没有作答记录，不能复习）
--   weak_n    当前得分 < :score_line 的点有几个
--   scores    得分最低的 :top 个点「名 分」，「、」连起来；没有低分点是空串
--   names     本轮复习会涉及的点的名字，最多 :top 个，多了加「…」：先是低分点
--             （低的在前），没有低分点就是最近答错的点
--   link      复习薄弱点的地址（#做题?mode=review，界面名编过码）
--
-- :level  认出 N5–N1 就只看这一级（这个点有这一级的题），认不出不限。
WITH lvl AS (
  SELECT CASE WHEN instr(upper(coalesce(:level, '')), 'N5') > 0 THEN 'N5'
              WHEN instr(upper(coalesce(:level, '')), 'N4') > 0 THEN 'N4'
              WHEN instr(upper(coalesce(:level, '')), 'N3') > 0 THEN 'N3'
              WHEN instr(upper(coalesce(:level, '')), 'N2') > 0 THEN 'N2'
              WHEN instr(upper(coalesce(:level, '')), 'N1') > 0 THEN 'N1'
              ELSE '' END AS v
),
inlvl AS (
  SELECT DISTINCT i.point FROM question q JOIN item i ON i.code = q.item, lvl
  WHERE lvl.v = '' OR q.level = lvl.v
),
low AS (
  SELECT s.point, coalesce(n.label, s.point) AS label, s.value, s.id
  FROM score s LEFT JOIN node n ON n.code = s.point
  WHERE s.learner = :learner
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
    AND s.value < CAST(:score_line AS INTEGER)
    AND s.point IN (SELECT point FROM inlvl)
),
lowtop AS (
  SELECT label, value FROM low ORDER BY value, id DESC LIMIT CAST(:top AS INTEGER)
),
wrongpt AS (
  SELECT coalesce(n.label, a.point) AS label, max(a.id) AS last
  FROM attempt a LEFT JOIN node n ON n.code = a.point
  WHERE a.learner = :learner AND a.correct = 0
    AND a.point IN (SELECT point FROM inlvl)
  GROUP BY a.point
),
wrongtop AS (
  SELECT label FROM wrongpt ORDER BY last DESC LIMIT CAST(:top AS INTEGER)
)
SELECT
  (SELECT count(*) FROM attempt WHERE learner = :learner) AS answers,
  (SELECT count(*) FROM low) AS weak_n,
  coalesce((SELECT group_concat(label || ' ' || value, '、') FROM lowtop), '') AS scores,
  CASE WHEN (SELECT count(*) FROM low) > 0
       THEN (SELECT group_concat(label, '、') FROM lowtop)
            || CASE WHEN (SELECT count(*) FROM low) > CAST(:top AS INTEGER) THEN '…' ELSE '' END
       ELSE coalesce((SELECT group_concat(label, '、') FROM wrongtop), '')
            || CASE WHEN (SELECT count(*) FROM wrongpt) > CAST(:top AS INTEGER) THEN '…' ELSE '' END
  END AS names,
  '#%E5%81%9A%E9%A2%98?mode=review' AS link
