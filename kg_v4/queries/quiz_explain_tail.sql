SELECT :expl || char(10) || char(10) || CASE WHEN :lang = 'ja' THEN 'ポイント：' ELSE '考的是：' END || :name || CASE WHEN :lt = '' THEN '' ELSE '　' || :lt END AS t
