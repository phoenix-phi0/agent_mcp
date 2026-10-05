-- 按做题情况算一个人在一个知识点上的掌握得分（0–100），并跟当前分比。
-- 只算不写：写不写由 scripts/score_update.zs 看 changed 决定。
--
-- 算法（参数都由调用方给，默认值集中在 scripts/score_update.zs）：
--
--   取这个点最近 :window 次作答，越近权重越大：第 k 次（k=0 是最近一次）
--   的基础权重是 :decay^k。再乘难度权重：
--     进阶题答对  × :hard_right   难题做对了更说明问题
--     基础题答错  × :easy_wrong   基础题都错，该多罚
--     其余（以及题库里查不到的作答，比如 /learn/answer 只报对错的）× 1
--   得分 = round(100 * (Σw·对 + :prior_right) / (Σw + :prior_right + :prior_wrong))
--
--   先验 a、b 是「虚拟的几道题」：答得少时分数被往 a/(a+b) 拉，答对一道
--   不会是 100。衰减让有效题数封顶（Σw 最多约 1/(1-decay)），所以全对的
--   分数有上限（基础题全对约 84），要往上走得做对进阶题。
--
-- 题型不单独加权：题库里「进阶」恰好就是接续题和找错句（基础是挖空和
-- 意思），再按题型加一遍等于同一件事算两次。
--
-- 幂：不用 pow()——SQLite 的数学函数要编译时打开，别处的 sqlite 不一定有。
-- 用递归 CTE 连乘出 0..window-1 的权重表。数值一律 1.0* / CAST 成 REAL，
-- 免得整数除法。
--
-- 出一行：
--   n        算进去的作答数（0 表示这个点没作答，不该打分）
--   value    算出来的分
--   prev     当前分（最新一行，按 id），没打过是 NULL
--   changed  1 = 跟当前分不同（或者还没打过），该记一行
--   label    知识点名，给「推量判断 得分 42 → 51」用
WITH RECURSIVE
p AS (
  SELECT CAST(:window AS INTEGER) AS win,
         CAST(:decay AS REAL) AS dec,
         CAST(:prior_right AS REAL) AS a,
         CAST(:prior_wrong AS REAL) AS b,
         CAST(:hard_right AS REAL) AS hard,
         CAST(:easy_wrong AS REAL) AS easy
),
pw(k, w) AS (
  SELECT 0, 1.0
  UNION ALL
  SELECT pw.k + 1, pw.w * p.dec FROM pw, p WHERE pw.k + 1 < p.win
),
r AS (
  SELECT x.correct,
         q.difficulty,
         ROW_NUMBER() OVER (ORDER BY x.id DESC) - 1 AS k
  FROM attempt x
  LEFT JOIN question q ON q.code = x.item
  WHERE x.learner = :learner AND x.point = :point
),
t AS (
  SELECT r.correct,
         pw.w * CASE WHEN r.correct = 1 AND r.difficulty = '进阶' THEN p.hard
                     WHEN r.correct = 0 AND r.difficulty = '基础' THEN p.easy
                     ELSE 1.0 END AS w
  FROM r JOIN pw ON pw.k = r.k, p
),
s AS (
  SELECT count(*) AS n,
         coalesce(sum(t.w * t.correct), 0.0) AS hit,
         coalesce(sum(t.w), 0.0) AS tot
  FROM t
),
v AS (
  SELECT s.n,
         CAST(round(100.0 * (s.hit + p.a) / (s.tot + p.a + p.b)) AS INTEGER) AS value,
         (SELECT c.value FROM score c
           WHERE c.learner = :learner AND c.point = :point
           ORDER BY c.id DESC LIMIT 1) AS prev
  FROM s, p
)
SELECT v.n, v.value, v.prev,
       CASE WHEN v.prev IS NULL OR v.prev <> v.value THEN 1 ELSE 0 END AS changed,
       coalesce((SELECT label FROM node WHERE code = :point), :point) AS label
FROM v
