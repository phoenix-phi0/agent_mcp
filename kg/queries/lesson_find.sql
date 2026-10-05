-- 按关键词找最相关的课文。问老师用（routes/teacher.zs）。
--
-- :keywords  意图判定给的检索词，JSON 数组；不是数组就当一个词
-- :message   学习者的原话。条目名（ようだ、てから……）出现在原话里也算命中，
--            意图判定坏了、没给关键词时靠它兜底
-- :level     提到的等级（N4），同分时同等级的排前面
-- :quiz      1 = 只要能出题的：标题或条目名命中（strong）且这一课有题。
--            出题时用——光是讲解里提了一句的课不能当成「这一课的题」
--
-- 打分：标题、条目名命中 3，原话里出现条目名按条目名的字数算（てから 比
-- から 长，「てから怎么用」先找到 てから 那课），一句话、接续、讲解命中各 1。
-- 词去掉 ～ 〜 再比，「～ようだ」和「ようだ」一样。
--
-- body 是给模型看的课文正文（标题、一句话、接续、讲解、例句原文），末尾带
-- 两个换行，脚本里直接一课接一课拼起来。link 是做题页按课文出题的地址，
-- 写法跟 kg/__main__.py 的 quiz_link 一样（界面名编过码）；read 是教材页读
-- 这一课的地址（跟 lesson_list 的 href 一样），老师回复里的「读课文」用它。
WITH kw AS (
  SELECT DISTINCT replace(replace(trim(value), '～', ''), '〜', '') AS k
  FROM json_each(CASE WHEN json_valid(:keywords) AND json_type(:keywords) = 'array'
                      THEN :keywords ELSE json_array(:keywords) END)
  WHERE replace(replace(trim(value), '～', ''), '〜', '') <> ''
),
labels AS (
  SELECT il.lesson, i.label
  FROM item_lesson il JOIN item i ON i.code = il.item
),
hit AS (
  SELECT l.code,
         (SELECT count(*) FROM kw WHERE instr(l.title, kw.k) > 0) AS t,
         (SELECT count(*) FROM kw, labels b
           WHERE b.lesson = l.code AND (b.label = kw.k OR
                 (length(kw.k) >= 2 AND instr(b.label, kw.k) > 0))) AS b,
         (SELECT coalesce(sum(length(b.label)), 0) FROM labels b
           WHERE b.lesson = l.code AND length(b.label) >= 2
             AND instr(:message, b.label) > 0) AS m,
         (SELECT count(*) FROM kw WHERE instr(l.summary, kw.k) > 0) AS s,
         (SELECT count(*) FROM kw WHERE instr(coalesce(l.formation, ''), kw.k) > 0) AS f,
         (SELECT count(*) FROM kw WHERE instr(l.explanation, kw.k) > 0) AS e
  FROM lesson l
),
scored AS (
  SELECT l.*, (h.t + h.b) * 3 + h.m * 2 + h.s + h.f + h.e AS score,
         (h.t + h.b + h.m) > 0 AS strong,
         (SELECT count(*) FROM question q WHERE q.lesson = l.code) AS n
  FROM lesson l JOIN hit h ON h.code = l.code
)
SELECT code, level, title, summary, n, score, strong,
       '#%E5%81%9A%E9%A2%98?lesson=' || code AS link,
       '#%E6%95%99%E6%9D%90?lesson=' || code AS read,
       '《' || title || '》（' || level || '，课文 ' || code || '）' || char(10)
         || summary || char(10)
         || CASE WHEN coalesce(formation, '') <> '' THEN '接续：' || formation || char(10) ELSE '' END
         || explanation || char(10)
         || CASE WHEN coalesce(examples, '') <> '' THEN '例句：' || examples || char(10) ELSE '' END
         || char(10) AS body
FROM scored
WHERE score > 0
  AND (CAST(:quiz AS INTEGER) = 0 OR (strong AND n > 0))
ORDER BY score DESC, (level = upper(trim(:level))) DESC, n DESC, code
LIMIT 2
