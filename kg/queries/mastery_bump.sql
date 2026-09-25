-- 汇总加一笔：没有这一行就建，有就累加。
--
-- 靠 (learner, point) 上的唯一索引来认「同一行」，那个索引由 py -m kg
-- setup 建（.entity 表达不了多列唯一，跟边和对照的做法一样）。
INSERT INTO mastery(learner, point, right, total, mastered, updated)
VALUES(:learner, :point, CAST(:correct AS INTEGER), 1, 0, datetime('now'))
ON CONFLICT(learner, point) DO UPDATE SET
  right = right + CAST(:correct AS INTEGER),
  total = total + 1,
  updated = datetime('now')
