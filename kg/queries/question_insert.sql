-- 插一道题。导入前已整表清空，所以是纯插入。
--
-- 条目不在库里就不插（影响 0 行），导入接口据此计数、报告是哪道题。
-- 题号重复撞主键、缺题号或缺答案撞非空约束，都会让整个导入回滚——那是
-- 数据文件坏了，不该静默吞掉。
--
-- 等级从课程名取：bunpou_n5 → N5。
INSERT INTO question(code, course, level, kind, difficulty, qtype, stem,
                     answer, accept, explain, item, lesson)
SELECT NULLIF(:code, ''), :course, UPPER(SUBSTR(:course, -2)), :kind,
       NULLIF(:difficulty, ''), :qtype, :stem, NULLIF(:answer, ''),
       NULLIF(:accept, ''), NULLIF(:explain, ''), :item, NULLIF(:lesson, '')
WHERE EXISTS (SELECT 1 FROM item WHERE code = :item)
