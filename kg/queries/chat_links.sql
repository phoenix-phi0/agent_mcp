-- 把老师回复要带的几个链接拼成 JSON 数组 [{"href":…,"text":…}]：脚本里
-- 「解析JSON」成列表放进消息的 links，原文写进 chat_message.links。
-- 在 SQL 里拼是为了转义交给 json_object（课文标题里有什么字都不怕）。
--
-- :href1..:href3 / :text1..:text3  按顺序，href 空的那个跳过；都空就是 []
WITH v(o, h, t) AS (
  VALUES (1, :href1, :text1), (2, :href2, :text2), (3, :href3, :text3)
)
SELECT coalesce((SELECT json_group_array(json_object('href', h, 'text', coalesce(t, '')))
                 FROM (SELECT h, t FROM v WHERE coalesce(h, '') <> '' ORDER BY o)), '[]')
