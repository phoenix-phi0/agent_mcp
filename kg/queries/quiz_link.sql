-- 做题页的地址。问老师在出题时找不到具体课文，退到按等级、考点；都没有
-- 就是不带参数的做题页。等级从字里认 N5–N1（模型可能写成 n4、「N4级」），
-- 认不出、考点不在枚举里的当没给。
--
-- 按课文的地址跟 lesson_find.sql 的 link 一样；按等级、考点的由做题页的
-- 「载入」（/quiz/lesson）接住，直接出题、把顶栏填成这个等级考点。
-- label 是给人看的范围说明。
WITH p AS (
  SELECT CASE WHEN instr(upper(:level), 'N5') > 0 THEN 'N5'
              WHEN instr(upper(:level), 'N4') > 0 THEN 'N4'
              WHEN instr(upper(:level), 'N3') > 0 THEN 'N3'
              WHEN instr(upper(:level), 'N2') > 0 THEN 'N2'
              WHEN instr(upper(:level), 'N1') > 0 THEN 'N1'
              ELSE '' END AS level,
         CASE WHEN trim(:kind) IN ('挖空', '意思', '接续', '找错句')
              THEN trim(:kind) ELSE '' END AS kind
)
SELECT level, kind,
       '#%E5%81%9A%E9%A2%98' || CASE
         WHEN level <> '' AND kind <> '' THEN '?level=' || level || '&kind=' || kind
         WHEN level <> '' THEN '?level=' || level
         WHEN kind <> '' THEN '?kind=' || kind
         ELSE '' END AS link,
       CASE
         WHEN level <> '' AND kind <> '' THEN level || '・' || kind
         WHEN level <> '' THEN level || '（考点不限）'
         WHEN kind <> '' THEN kind || '（等级不限）'
         ELSE '' END AS label
FROM p
