-- 课文整表清空，导入时重灌。课文是内容不是学习记录，文件是唯一来源。
-- 先清 item_lesson（它引用 lesson），这里只清 lesson——两条语句分两个文件，
-- 写库表一次只执行一条。
DELETE FROM lesson
