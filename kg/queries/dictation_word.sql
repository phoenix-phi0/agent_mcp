-- 题卡上的一个词。bare 是去掉等级前缀的意思，level 是前缀里的等级（没有是空）。
-- label 是「汉字【读音】意思」（没汉字或汉字就是假名时是「假名 意思」），批改和错词
-- 列表用。hint 是「提示」给的：首个假名、一共几个字（按读音算）。
-- head 是题卡抬头：「N4・看中文写日语」，没等级就只写方向。
SELECT w.id, coalesce(w.kanji, '') AS kanji, w.kana, coalesce(w.meaning, '') AS meaning,
       CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 2, 2) ELSE '' END AS level,
       trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5) ELSE coalesce(w.meaning, '') END) AS bare,
       CASE WHEN coalesce(w.kanji, '') <> '' AND w.kanji <> w.kana
            THEN w.kanji || '【' || w.kana || '】' ELSE w.kana || ' ' END
       || trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5) ELSE coalesce(w.meaning, '') END) AS label,
       '提示：第一个假名是「' || substr(w.kana, 1, 1) || '」，读音一共 ' || length(w.kana) || ' 个字' AS hint,
       CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 2, 2) || '・' ELSE '' END
       || CASE WHEN :direction = 'reading' THEN '看汉字写读音' ELSE '看中文写日语' END AS head
FROM word w
WHERE w.id = CAST(:word AS INTEGER)
