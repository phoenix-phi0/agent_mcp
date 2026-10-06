-- 教材页切换系列：记下这个学习者选的系列。只认下拉里有的系列（series 表里
-- sort ≥ 0 的），别的影响 0 行、偏好不变——地址、表单里伪造一个系列编号
-- 不会把人带进一个没有课的系列。跟原来一样就不写（updated 不跟着每次搜索变）。
INSERT INTO learner_pref(learner, series, updated)
SELECT :learner, :series, datetime('now', 'localtime')
WHERE coalesce(:learner, '') <> ''
  AND EXISTS (SELECT 1 FROM series WHERE code = :series AND sort >= 0)
ON CONFLICT(learner) DO UPDATE SET series = excluded.series, updated = excluded.updated
WHERE learner_pref.series <> excluded.series
