-- 判定模型回的 JSON 归成一个结论（scripts/relay_judge.zs）：
--   已传达    delivered 是，必须准确的信息没说错（accurate 不是「否」；没给必须准确
--             的信息时 accurate 不看）
--   有误      delivered 是，但给了必须准确的信息、accurate 是「否」
--   未传达    delivered 否
--   判定失败  delivered 缺了 / 不认得（模型回了 JSON 但不是要的样子）
-- 是 / 否 也认 true/false、yes/no、1/0（问JSON 解析出来的布尔展开成 True/False）。
WITH v AS (
  SELECT lower(trim(coalesce(:delivered, ''))) AS d,
         lower(trim(coalesce(:accurate, ''))) AS a,
         trim(coalesce(:facts, '')) AS facts
)
SELECT CASE
  WHEN d IN ('是', 'true', 'yes', '1') THEN
    CASE WHEN facts <> '' AND a IN ('否', 'false', 'no', '0') THEN '有误' ELSE '已传达' END
  WHEN d IN ('否', 'false', 'no', '0') THEN '未传达'
  ELSE '判定失败' END AS verdict
FROM v
