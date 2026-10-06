-- 按课文练习时顶栏那句说明，顺带这一课有几道题、读这一课和课文表的地址
-- （一轮做完时给「回教材」「换一课」用），和请老师讲这一课的地址（#问老师?
-- lesson=…，问老师页进去就发出讲解请求）。没有这一课就查不到行。
--
-- 「本课《标题》+ 易混对比」：一轮是本课 1 道加别的条目各 1 道。有易混对比
-- （contrast 里跟本课条目成对）的课写「+ 易混对比」，没有的写「+ 同级对比」
-- ——混进来的题从哪儿来，跟 question_pick_lesson 一致。
--
-- lq 是「课的题」：hanabira 的题库按课文编号打了标（question.lesson），照旧按
-- 标；别的系列的课没有自己的题，按映射取——挂着的条目（item_lesson）的题，
-- 加上直接挂的知识点（lesson_point）下所有条目的题。几个课文查询里是同一段。
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
)
SELECT l.code, l.level, l.title, l.series,
       (SELECT count(*) FROM lq WHERE lq.lesson = l.code) AS n,
       '本课《' || l.title || '》'
       || CASE WHEN EXISTS (
                 SELECT 1 FROM contrast c
                 WHERE c.a IN (SELECT item FROM lq WHERE lesson = l.code)
                    OR c.b IN (SELECT item FROM lq WHERE lesson = l.code))
               THEN '+ 易混对比' ELSE '+ 同级对比' END AS scope,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS back,
       '#%E6%95%99%E6%9D%90' AS more,
       '#%E9%97%AE%E8%80%81%E5%B8%88?lesson=' || l.code AS explain
FROM lesson l
WHERE l.code = :lesson
