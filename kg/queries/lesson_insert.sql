-- 插一课。导入前已整表清空，所以是纯插入；文件里重复的编号会撞主键报错，
-- 整个导入回滚——重复是数据错误，不该静默吞掉。
INSERT INTO lesson(code, level, title, summary, explanation, formation,
                   examples, changed, source_title)
VALUES(NULLIF(:code, ''), :level, :title, :summary, :explanation, NULLIF(:formation, ''),
       NULLIF(:examples, ''), CAST(:changed AS INTEGER), NULLIF(:source_title, ''))
