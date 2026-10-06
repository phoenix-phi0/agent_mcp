-- 撤下一个系列：sort 改成 -1，教材页的下拉不再列它（series_options 只列
-- sort ≥ 0），选过它的学习者回到 hanabira（series_current 同样只认 sort ≥ 0）。
-- 偏好那一行不动——那是学习者的数据。
UPDATE series SET sort = -1 WHERE code = :series AND code <> 'hanabira'
