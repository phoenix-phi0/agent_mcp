-- 插一课。导入前这个系列已清空，所以是纯插入；文件里重复的编号（或者跟别的
-- 系列的课撞了编号）会撞主键报错，整个导入回滚——重复是数据错误，不该静默吞掉。
-- seq 是课序（线性教材填，hanabira 空）：空串、不是整数的都当没有。
INSERT INTO lesson(code, level, title, summary, explanation, formation,
                   examples, changed, source_title, series, seq)
VALUES(NULLIF(:code, ''), :level, :title, :summary, :explanation, NULLIF(:formation, ''),
       NULLIF(:examples, ''), CAST(:changed AS INTEGER), NULLIF(:source_title, ''),
       :series,
       CASE WHEN :seq <> '' AND :seq NOT GLOB '*[^0-9]*' THEN CAST(:seq AS INTEGER) END)
