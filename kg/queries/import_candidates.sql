-- 给模型的候选清单：已有的条目和知识点，一行一个，拼成一段文本。
--   条目 te-kara｜てから｜属于 f-time（时间先后）
--   知识点 f-time｜时间先后
-- :level_hint 是 N5–N1 时按等级预筛条目：hanabira 里挂在这个等级的课上的
-- 条目，加上没挂任何课的（不知道等级的不能漏）；「全部」不筛。知识点不多
-- （几十个），总是全给。控制提示词长度用。
SELECT
  (SELECT group_concat(line, char(10)) FROM (
     SELECT '条目 ' || i.code || '｜' || i.label || '｜属于 ' || i.point
            || coalesce('（' || n.label || '）', '') AS line
     FROM item i LEFT JOIN node n ON n.code = i.point
     WHERE coalesce(:level_hint, '全部') NOT IN ('N5', 'N4', 'N3', 'N2', 'N1')
        OR NOT EXISTS (SELECT 1 FROM item_lesson il WHERE il.item = i.code)
        OR EXISTS (SELECT 1 FROM item_lesson il JOIN lesson l ON l.code = il.lesson
                   WHERE il.item = i.code AND l.level = :level_hint)
     ORDER BY i.point, i.code))
  || char(10) ||
  (SELECT group_concat(line, char(10)) FROM (
     SELECT '知识点 ' || code || '｜' || label AS line FROM node ORDER BY code))
