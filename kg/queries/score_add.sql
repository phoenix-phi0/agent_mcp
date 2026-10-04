-- 记一次打分。只进不改：改分就是再记一行，当前分取最新的那行。
--
-- 分值必须是 0–100 的整数。实体表达不了区间，所以在这儿查：不合格就
-- 一行都不写（影响 0 行），接口据此报 400。
--
-- 参数一律是字符串，**要先确认全是数字再 CAST**：CAST('4.5' AS INTEGER)
-- 是 4、CAST('abc' AS INTEGER) 是 0、CAST('-1' AS INTEGER) 是 -1——只查
-- 区间的话，前两个都会悄悄写进去，而且不报错。
--   :value <> ''                  空串
--   NOT GLOB '*[^0-9]*'           有任何一个非数字字符（小数点、负号、空格）
--   length <= 3                   防一长串 0 开头的数字（CAST 前先挡掉）
--
-- 知识点存不存在由接口先查（node_exists），这里不再判。
--
-- at 不填，让列的默认值填：实体里「默认 现在」渲染成
-- datetime('now','localtime')，是本地时间。这里要是自己写 datetime('now')
-- 就是 UTC，差 9 小时，历史上看到的打分时间跟钟对不上。
INSERT INTO score(learner, point, value)
SELECT :learner, :point, CAST(:value AS INTEGER)
WHERE :value <> ''
  AND :value NOT GLOB '*[^0-9]*'
  AND length(:value) <= 3
  AND CAST(:value AS INTEGER) BETWEEN 0 AND 100
