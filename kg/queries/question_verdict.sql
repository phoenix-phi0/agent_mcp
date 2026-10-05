-- 判完给界面看的两段：text 是一行结论（对错、正确答案），explain 是解析，
-- 最后是这道题考的条目和对应的课文（没挂课文就不写那半句）。分两段是为了
-- 题卡上把「下一题」夹在中间：结论下面紧跟着按钮，长的解析排在按钮后面，
-- 不用滚到底才点得到（用的人说过「下一题太靠下」）。
--
-- :shown 是正确答案在界面上的字母——选择题的选项打乱过，题库里的原字母
-- （q.answer）跟界面上对不上。不给（接续题）就用 q.answer。
SELECT
  CASE WHEN CAST(:correct AS INTEGER) = 1 THEN '○ 答对了'
       ELSE '✗ 正确答案是 ' || COALESCE(NULLIF(:shown, ''), q.answer) END AS text,
  COALESCE(NULLIF(q.explain, '') || char(10) || char(10), '') || '考的是：' || i.label
  || COALESCE('　课文《' || l.title || '》' || l.summary, '') AS explain
FROM question q
JOIN item i ON i.code = q.item
LEFT JOIN lesson l ON l.code = q.lesson
WHERE q.code = :code
