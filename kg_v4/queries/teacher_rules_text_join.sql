SELECT CASE WHEN :a = '' THEN :b ELSE :a || char(10) || :b END
