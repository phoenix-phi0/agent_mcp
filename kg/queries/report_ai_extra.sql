-- AI 学情总结的提示词材料（progress_brief 之外的）：常错条目、最近 10 道作答、
-- 默写、问老师问过什么。每样一段文字，没有就写「无」以外的明确说法。只读。
WITH wrong AS (
  SELECT i.label || '（错 ' || sum(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END)
         || ' / 共 ' || count(*) || '）' AS s,
         sum(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS w
  FROM attempt a
  JOIN question q ON q.code = a.item
  JOIN item i ON i.code = q.item
  WHERE a.learner = :student
  GROUP BY i.code
  HAVING w > 0
  ORDER BY w DESC
  LIMIT 8
),
recent AS (
  SELECT a.at || ' ' || coalesce(n.label, a.point) || '：'
         || substr(coalesce(q.stem, ''), 1, 30) || ' → ' || coalesce(nullif(a.answer, ''), '（没记）')
         || (CASE WHEN a.correct = 1 THEN ' 对' ELSE ' 错' END) AS s
  FROM attempt a
  LEFT JOIN node n ON n.code = a.point
  LEFT JOIN question q ON q.code = a.item
  WHERE a.learner = :student
  ORDER BY a.id DESC
  LIMIT 10
),
asks AS (
  SELECT substr(content, 1, 40) AS s
  FROM chat_message
  WHERE learner = :student AND role <> 'teacher'
  ORDER BY id DESC
  LIMIT 5
),
dict AS (
  SELECT count(*) AS n, coalesce(sum(correct), 0) AS r, count(DISTINCT word) AS words
  FROM word_attempt WHERE learner = :student
)
SELECT coalesce((SELECT group_concat(s, '；') FROM wrong), '没有答错过的条目') AS wrong_text,
       coalesce((SELECT group_concat(s, '；') FROM recent), '还没有作答记录') AS recent_text,
       coalesce((SELECT group_concat(s, '；') FROM asks), '没有问过老师') AS ask_text,
       CASE WHEN dict.n = 0 THEN '还没有默写过'
            ELSE '默写过 ' || dict.words || ' 个词、' || dict.n || ' 次，正确率 ' || (dict.r * 100 / dict.n) || '%'
       END AS dict_text
FROM dict
