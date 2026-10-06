-- 汇总加一笔：没有这一行就建，有就累加。
--
-- 靠 (learner, point) 上的唯一索引来认「同一行」，那个索引写在实体里
-- （learn.entity 的「唯一 learner point」），老库由「迁移 只加」补。
--
-- updated 用本地时间，跟实体里「默认 现在」一致（datetime('now') 是 UTC）。
-- 这一列在实体上没有默认值，只能在这儿写。
INSERT INTO mastery(learner, point, right, total, mastered, updated)
VALUES(:learner, :point, CAST(:correct AS INTEGER), 1, 0, datetime('now','localtime'))
ON CONFLICT(learner, point) DO UPDATE SET
  right = right + CAST(:correct AS INTEGER),
  total = total + 1,
  updated = datetime('now','localtime')
