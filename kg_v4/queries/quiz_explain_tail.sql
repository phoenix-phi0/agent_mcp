SELECT :expl || char(10) || char(10) || '考的是：' || :name || CASE WHEN :lt = '' THEN '' ELSE '　' || :lt END AS t
