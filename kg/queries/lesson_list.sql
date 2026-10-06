-- 教材页的课文表：按等级筛、按关键字搜。
--
-- :lesson_level  全部 / N5..N1，空串和「全部」一样
-- :keyword       在标题、一句话、挂着的条目名里找，整段当一个词（中间可以
--                有空格：「A は B」）。去掉首尾空白（含全角空格、换行）；
--                % _ 转义掉，搜的是字面量。
--                LIKE 对英文字母不分大小写
--
-- :series       只列这个系列的课（教材页的「系列」下拉，路由里取学习者的偏好）
--
-- lq 是「课的题」：hanabira 的题库按课文编号打了标（question.lesson），照旧按
-- 标；别的系列的课没有自己的题，按映射取——挂着的条目（item_lesson）的题，
-- 加上直接挂的知识点（lesson_point）下所有条目的题。几个课文查询里是同一段。
--
-- qcount 是这一课的题数；href 是点标题打开这一课的地址（界面名编过码，
-- 跟 lesson_find.sql 的做题链接一个写法）。N5 在前（字符串倒序），同级按课序
-- （有 seq 的）、编号排。
WITH lq AS (
  SELECT q.lesson AS lesson, q.code, q.item FROM question q WHERE q.lesson IS NOT NULL
  UNION
  SELECT l.code, q.code, q.item FROM lesson l
  JOIN item_lesson il ON il.lesson = l.code JOIN question q ON q.item = il.item
  WHERE l.series <> 'hanabira'
  UNION
  SELECT l.code, q.code, q.item FROM lesson l
  JOIN lesson_point lp ON lp.lesson = l.code JOIN item i ON i.point = lp.point
  JOIN question q ON q.item = i.code
  WHERE l.series <> 'hanabira'
),
qn AS (
  SELECT lesson, count(*) AS n FROM lq GROUP BY lesson
),
w AS (
  SELECT trim(coalesce(:keyword, ''), ' 　' || char(9, 10, 13)) AS kw
),
k AS (
  SELECT '%' || replace(replace(replace(kw, '\', '\\'), '%', '\%'), '_', '\_') || '%' AS pat,
         kw = '' AS any_kw
  FROM w
)
SELECT l.code, l.level, l.title, l.summary,
       coalesce((SELECT n FROM qn WHERE qn.lesson = l.code), 0) AS qcount,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS href
FROM lesson l, k
WHERE l.series = :series
  AND (coalesce(:lesson_level, '') IN ('', '全部') OR l.level = :lesson_level)
  AND (k.any_kw
       OR l.title LIKE k.pat ESCAPE '\'
       OR l.summary LIKE k.pat ESCAPE '\'
       OR EXISTS (SELECT 1 FROM item_lesson il JOIN item i ON i.code = il.item
                  WHERE il.lesson = l.code AND i.label LIKE k.pat ESCAPE '\'))
ORDER BY l.level DESC, coalesce(l.seq, 0), l.code
