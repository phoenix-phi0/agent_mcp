-- 一个系列的课清空，导入时重灌。课文是内容不是学习记录，文件是唯一来源；
-- 只删这个系列的，别的系列一课不动。先清 item_lesson、lesson_point（它们
-- 引用 lesson），这里只清 lesson——写库表一次只执行一条。
DELETE FROM lesson WHERE series = :series
