-- 读一课：教材页的阅读视图。没有这一课就查不到行。
--
-- head      抬头：《标题》 等级 第N课（课号）。有课序（seq，线性教材）的「第N课」
--           就是课序；没有的（hanabira）课号末尾三位数就是「第N课」。问老师时说
--           「讲讲 N5 第46课」「讲一下 hb-n5-046」都认（lesson_ref.sql）
-- series / series_label  这一课属于哪个系列、系列名（阅读顶栏上显示）
-- practice  做题页按这一课出题的地址；这一课没有题时是空串——界面上的
--           「练这一课」地址空就不画
-- quiz_note 没有题时的那句说明，有题时空串
-- ask/back  问老师页、回课文表的地址（界面名编过码）
-- explain   请老师讲解这一课：#问老师?lesson=…，问老师页「触发」teacher_send，
--           进去就发出讲解请求
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
SELECT l.code, l.level, l.title, l.summary,
       coalesce(l.formation, '') AS formation,
       l.explanation,
       n.qcount,
       '《' || l.title || '》　' || l.level || '　第'
         || coalesce(l.seq, CAST(substr(l.code, -3) AS INTEGER))
         || '课（' || l.code || '）' AS head,
       l.series, coalesce(s.label, l.series) AS series_label,
       CASE WHEN n.qcount > 0 THEN '#%E5%81%9A%E9%A2%98?lesson=' || l.code ELSE '' END AS practice,
       CASE WHEN n.qcount > 0 THEN '这一课有 ' || n.qcount || ' 道题'
            ELSE '这一课还没有题，可以先问老师' END AS quiz_note,
       '#%E9%97%AE%E8%80%81%E5%B8%88' AS ask,
       '#%E9%97%AE%E8%80%81%E5%B8%88?lesson=' || l.code AS explain,
       '#%E6%95%99%E6%9D%90' AS back
FROM lesson l
     LEFT JOIN series s ON s.code = l.series,
     (SELECT count(*) AS qcount FROM lq WHERE lesson = :lesson) n
WHERE l.code = :lesson
