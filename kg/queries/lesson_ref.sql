-- 学习者的原话有没有指名某一课，指的是哪一课。问老师用（routes/teacher.zs）：
-- 认出来了就讲这一课（课文正文、学习者在这一课的答题情况），不靠关键词去猜。
--
-- :message  学习者的原话
-- :level    意图判定给的等级（N5），「第46课」好几个等级都有时先取它
-- :learner  学习者。「这课」指的是这个人最近一次对话里老师参考的那一课；
--           「第N课」只在他当前的系列里认（learner_pref，没记过是 hanabira）
--
-- 按顺序认，先认出来的算：
--   课号     原话里有课号（hb-n5-046，不分大小写），哪个系列的都认——课号全库
--            唯一，说出来就不会认错。教材页阅读视图的抬头上有
--   第N课    只在当前系列里认。有课序（seq，线性教材）的课：「第N课」就是课序 N，
--            系列里课序不重，不看等级。没有课序的（hanabira）：「第46课」
--            「第046课」是课号末尾的三位数，提到了等级只认那一级；没提等级时
--            只有一个等级有这个号才认，几个等级都有就不猜，candidates 列出
--            这几课（老师回复里请学习者说是哪一级）
--   这课     「这课」「这一课」「本课」「这节课」「这篇课文」：最近一条带课文
--            编号的对话记录（从教材页点「请老师讲解」、问过某一课之后接着问）
--
-- asked = 1：原话在指名某一课（有课号的样子、「第…课」、「这课」），不管认
-- 没认出来。课号的样子是「某个课号的前缀-」后面跟着字母或数字：前缀取库里
-- 课号第一个连字符之前那段（hb-n5-046 的 hb-），不写死哪个系列。认不出来时（「讲解第1课」：没有 001 号的课）老师回一句找不到、
-- 指去教材页，不拿别的课凑数，也不调模型。
--
-- candidates：「第N课」对上了几课、没认定时的那几课，《标题》（等级，课号）、
-- 顿号隔开；其余情况空串。
--
-- 原话先去掉空格（半角、全角）再比：「第 46 课」也认。
WITH said AS (
  SELECT lower(replace(replace(coalesce(:message, ''), ' ', ''), '　', '')) AS m
),
cur AS (
  SELECT coalesce((SELECT p.series FROM learner_pref p
                   WHERE p.learner = :learner
                     AND EXISTS (SELECT 1 FROM series s WHERE s.code = p.series)),
                  'hanabira') AS s
),
prefix AS (
  SELECT DISTINCT lower(substr(code, 1, instr(code, '-'))) AS p
  FROM lesson WHERE instr(code, '-') > 1
),
by_code AS (
  SELECT l.code FROM lesson l, said
  WHERE instr(said.m, lower(l.code)) > 0
  ORDER BY length(l.code) DESC, l.code
  LIMIT 1
),
no_hit AS (
  SELECT l.code, l.level, l.title FROM lesson l, said, cur
  WHERE l.series = cur.s
    AND ((l.seq IS NOT NULL AND instr(said.m, '第' || l.seq || '课') > 0)
         OR (l.seq IS NULL
             AND (instr(said.m, '第' || CAST(substr(l.code, -3) AS INTEGER) || '课') > 0
                  OR instr(said.m, '第' || substr(l.code, -3) || '课') > 0)
             AND (trim(coalesce(:level, '')) = '' OR l.level = upper(trim(:level)))))
),
by_no AS (
  SELECT code FROM no_hit WHERE (SELECT count(*) FROM no_hit) = 1
),
pronoun AS (
  SELECT (instr(m, '这课') + instr(m, '这一课') + instr(m, '本课')
          + instr(m, '这节课') + instr(m, '这篇课文')) > 0 AS yes
  FROM said
),
recent AS (
  SELECT c.lesson AS code FROM chat_message c
  WHERE c.learner = :learner AND coalesce(c.lesson, '') <> ''
    AND EXISTS (SELECT 1 FROM lesson l WHERE l.code = c.lesson)
  ORDER BY c.id DESC
  LIMIT 1
)
SELECT coalesce((SELECT code FROM by_code),
                (SELECT code FROM by_no),
                CASE WHEN (SELECT yes FROM pronoun) THEN (SELECT code FROM recent) END,
                '') AS code,
       CASE WHEN EXISTS (SELECT 1 FROM prefix WHERE said.m GLOB '*' || prefix.p || '[0-9a-z]*')
              OR said.m GLOB '*第[0-9]*课*'
              OR said.m GLOB '*第[一二三四五六七八九十百零两]*课*'
              OR (SELECT yes FROM pronoun)
            THEN 1 ELSE 0 END AS asked,
       CASE WHEN (SELECT count(*) FROM no_hit) > 1
            THEN (SELECT group_concat('《' || title || '》（' || level || '，' || code || '）', '、')
                  FROM (SELECT * FROM no_hit ORDER BY level DESC, code))
            ELSE '' END AS candidates
FROM said
