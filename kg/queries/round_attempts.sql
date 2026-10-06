-- 这一轮做过的题，拼成给老师（模型）看的一段文字，请老师总结用
-- （routes/quiz.zs 的 /quiz/summary）。一行：
--
--   n / ok_n      这一轮答了几道、对了几道
--   label         范围：按课练《标题》/ 复习薄弱点 / 自由练（等级、考点）
--   level         等级（按课练是那一课的，自由练是顶栏选的，复习不限），给进度摘要用
--   lesson        在练的课（自由练、复习是空串）
--   worst / worst_title / read / practice / explain
--                 错得最多的那一课（一样多先算在练的那课、再算最近做的；
--                 全对就是做得最多的），读课文、再练这一课、请老师讲这课
--                 （#问老师?lesson=…）的地址
--   round_key     这一轮是哪一轮：起点 - 最后一道作答的 id。同一轮没再答题就
--                 不变，/quiz/summary 用它认「这一轮总结过了」
--   text          每道题一段：知识点·条目、课文、对错、题干（不含选项）、
--                 选项、正确答案、学习者的作答、解析。最多最近 30 道，
--                 前面一行按知识点的对错统计
--
-- 「这一轮」= 这个人 attempt.id 比 quiz_state.round_from 大的作答（开一轮时
-- 记下的起点，见 quiz_state_pick.sql），只算做题页的题（item 是题号）。
--
-- 选择题的选项界面上打乱过，学习者看到的字母跟题库里的对不上：这里不给
-- 字母，正确答案和学习者选的都换成选项的内容（题干里「\nA. 内容」那几行）。
-- 题干、解析截短，控制提示词长度。
WITH st AS (
  SELECT round_from, coalesce(lesson, '') AS lesson, pick_level, pick_kind,
         coalesce(mode, '') AS mode
  FROM quiz_state WHERE learner = :learner
),
r AS (
  SELECT a.id, a.correct, coalesce(a.answer, '') AS mine,
         q.code, q.qtype, q.stem, q.answer AS akey, coalesce(q.explain, '') AS explain,
         q.lesson, l.title, l.level AS lesson_level,
         coalesce(n.label, a.point) AS point_label, coalesce(i.label, q.item) AS item_label
  FROM attempt a
  JOIN st
  JOIN question q ON q.code = a.item
  LEFT JOIN item i ON i.code = q.item
  LEFT JOIN node n ON n.code = a.point
  LEFT JOIN lesson l ON l.code = q.lesson
  WHERE a.learner = :learner AND a.id > st.round_from
),
ks(k) AS (VALUES ('A'), ('B'), ('C'), ('D')),
o0 AS (
  SELECT r.id, ks.k,
         substr(r.stem, instr(r.stem, char(10) || ks.k || '. ') + 3) AS rest
  FROM r, ks
  WHERE r.qtype = '选择' AND instr(r.stem, char(10) || ks.k || '. ') > 0
),
o AS (
  SELECT id, k, trim(substr(rest, 1, instr(rest || char(10), char(10)) - 1)) AS t FROM o0
),
num AS (
  SELECT r.*, row_number() OVER (ORDER BY r.id) AS no FROM r
),
line AS (
  SELECT x.id,
         x.no || '. 【' || x.point_label || '·' || x.item_label
         || coalesce('｜课文《' || x.title || '》', '') || '】'
         || CASE WHEN x.correct = 1 THEN '○ 答对' ELSE '✗ 答错' END || char(10)
         || '题目：' || substr(replace(trim(CASE WHEN x.qtype = '选择' AND instr(x.stem, char(10) || 'A. ') > 0
                                                 THEN substr(x.stem, 1, instr(x.stem, char(10) || 'A. ') - 1)
                                                 ELSE x.stem END), char(10), ' '), 1, 160) || char(10)
         || CASE WHEN x.qtype = '选择' THEN
              '选项：' || coalesce((SELECT group_concat(t, ' ／ ') FROM (SELECT t FROM o WHERE o.id = x.id ORDER BY k)), '') || char(10)
              || '正确答案：' || coalesce((SELECT t FROM o WHERE o.id = x.id AND o.k = x.akey), x.akey)
              || '；学习者选的：' || coalesce((SELECT t FROM o WHERE o.id = x.id AND o.k = x.mine),
                                           nullif(x.mine, ''), '（没有记下）')
            ELSE
              '正确答案：' || x.akey || '；学习者写的：' || coalesce(nullif(x.mine, ''), '（没有记下）')
            END || char(10)
         || '解析：' || CASE WHEN length(x.explain) > 120 THEN substr(x.explain, 1, 118) || '……'
                            ELSE x.explain END AS s
  FROM num x
  ORDER BY x.id DESC
  LIMIT 30
),
bypt AS (
  SELECT point_label || ' ' || sum(correct) || '/' || count(*) AS s, min(id) AS first
  FROM r GROUP BY point_label
),
w AS (
  SELECT r.lesson AS code, r.title
  FROM r, st
  WHERE r.lesson IS NOT NULL
  GROUP BY r.lesson
  ORDER BY sum(1 - r.correct) DESC, max(r.lesson = st.lesson) DESC, count(*) DESC, max(r.id) DESC
  LIMIT 1
)
SELECT
  (SELECT count(*) FROM r) AS n,
  (SELECT coalesce(sum(correct), 0) FROM r) AS ok_n,
  st.round_from || '-' || coalesce((SELECT max(id) FROM r), 0) AS round_key,
  st.lesson,
  CASE WHEN st.lesson <> ''
       THEN '按课练《' || coalesce((SELECT title FROM lesson WHERE code = st.lesson), st.lesson) || '》'
       WHEN st.mode = 'review' THEN '复习薄弱点'
       ELSE '自由练（等级 ' || st.pick_level || '，考点 ' || st.pick_kind || '）' END AS label,
  CASE WHEN st.lesson <> '' THEN coalesce((SELECT level FROM lesson WHERE code = st.lesson), '')
       WHEN st.mode = 'review' THEN ''
       WHEN st.pick_level <> '全部' THEN st.pick_level ELSE '' END AS level,
  coalesce((SELECT code FROM w), '') AS worst,
  coalesce((SELECT title FROM w), '') AS worst_title,
  coalesce((SELECT '#%E6%95%99%E6%9D%90?lesson=' || code FROM w), '') AS read,
  coalesce((SELECT '#%E5%81%9A%E9%A2%98?lesson=' || code FROM w), '') AS practice,
  coalesce((SELECT '#%E9%97%AE%E8%80%81%E5%B8%88?lesson=' || code FROM w), '') AS explain,
  CASE WHEN (SELECT count(*) FROM r) > 30
       THEN '（这一轮共 ' || (SELECT count(*) FROM r) || ' 道，下面只列最近 30 道）' || char(10) ELSE '' END
  || '按知识点（答对/答题）：' || coalesce((SELECT group_concat(s, '；') FROM (SELECT s FROM bypt ORDER BY first)), '无')
  || char(10) || char(10)
  || coalesce((SELECT group_concat(s, char(10) || char(10)) FROM (SELECT s FROM line ORDER BY id)), '') AS text
FROM st
