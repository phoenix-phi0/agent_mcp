-- 新教材的一课引用的条目、知识点里，库里没有的是哪些。导入时用
-- （routes/lesson.zs）：不是空串就整行拒收、写进报告，绝不新建条目或知识点。
--
-- :items   这一课映射的已有条目编号，JSON 数组（导入器把列表转成 JSON 文本）
-- :points  这一课直接挂的已有知识点编号，JSON 数组
-- 不是数组的（单个编号写成了字符串）当成一个；空串、空数组就是没有。
--
-- 回一句：「条目 a、b 不存在；知识点 c 不存在」，都在就是空串。
WITH it AS (
  SELECT DISTINCT trim(value) AS code
  FROM json_each(CASE WHEN json_valid(:items) AND json_type(:items) = 'array' THEN :items
                      WHEN coalesce(:items, '') = '' THEN '[]'
                      ELSE json_array(:items) END)
  WHERE trim(value) <> ''
),
pt AS (
  SELECT DISTINCT trim(value) AS code
  FROM json_each(CASE WHEN json_valid(:points) AND json_type(:points) = 'array' THEN :points
                      WHEN coalesce(:points, '') = '' THEN '[]'
                      ELSE json_array(:points) END)
  WHERE trim(value) <> ''
),
bad_it AS (
  SELECT group_concat(code, '、') AS s FROM it WHERE code NOT IN (SELECT code FROM item)
),
bad_pt AS (
  SELECT group_concat(code, '、') AS s FROM pt WHERE code NOT IN (SELECT code FROM node)
)
SELECT trim(coalesce('条目 ' || (SELECT s FROM bad_it) || ' 不存在', '')
            || CASE WHEN (SELECT s FROM bad_it) IS NOT NULL AND (SELECT s FROM bad_pt) IS NOT NULL
                    THEN '；' ELSE '' END
            || coalesce('知识点 ' || (SELECT s FROM bad_pt) || ' 不存在', ''))
