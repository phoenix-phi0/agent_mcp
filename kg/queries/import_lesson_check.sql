-- 一块的草稿课过存在性：items 只留 item 表里有的编号、points 只留 node 表里
-- 有的（去重，保持先后），库里没有的记进 dropped（「条目 x、y；知识点 z」）。
-- 绝不新建条目、知识点。SET 里的表达式看到的都是改之前的值，所以 dropped
-- 用的是原来的 items / points。
UPDATE import_lesson SET
  dropped = NULLIF(trim(
      coalesce('条目 ' || (SELECT group_concat(v, '、') FROM (
          SELECT DISTINCT trim(value) AS v FROM json_each(import_lesson.items)
          WHERE trim(value) <> '' AND trim(value) NOT IN (SELECT code FROM item))), '')
      || CASE WHEN (SELECT count(*) FROM json_each(import_lesson.items)
                    WHERE trim(value) <> '' AND trim(value) NOT IN (SELECT code FROM item)) > 0
               AND (SELECT count(*) FROM json_each(import_lesson.points)
                    WHERE trim(value) <> '' AND trim(value) NOT IN (SELECT code FROM node)) > 0
              THEN '；' ELSE '' END
      || coalesce('知识点 ' || (SELECT group_concat(v, '、') FROM (
          SELECT DISTINCT trim(value) AS v FROM json_each(import_lesson.points)
          WHERE trim(value) <> '' AND trim(value) NOT IN (SELECT code FROM node))), '')), ''),
  items = (SELECT coalesce(json_group_array(v), '[]') FROM (
      SELECT trim(value) AS v, min(CAST(key AS INTEGER)) AS k FROM json_each(import_lesson.items)
      WHERE trim(value) IN (SELECT code FROM item) GROUP BY trim(value) ORDER BY k)),
  points = (SELECT coalesce(json_group_array(v), '[]') FROM (
      SELECT trim(value) AS v, min(CAST(key AS INTEGER)) AS k FROM json_each(import_lesson.points)
      WHERE trim(value) IN (SELECT code FROM node) GROUP BY trim(value) ORDER BY k))
WHERE chunk = CAST(:chunk AS INTEGER)
