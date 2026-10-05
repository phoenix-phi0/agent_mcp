-- 只记下顶栏的等级，不出题：复习薄弱点但一道都没答过时（界面上「先按等级
-- 做几道」）把等级填成 :level 并记进库。
--
-- 为什么要进库：载入（/quiz/lesson）回的 form 之后，「进入时」的 /quiz/state
-- 按库里记的把顶栏再填一遍——库里没有的话又变回「全部」，点「开始」就不是
-- 按这一级出了（e2e 撞上过，看点得快不快时有时无）。
-- 只在等级还是「全部」（或者没有这一行）时改，选过的等级不动；当前题、
-- 计数都不碰。
INSERT INTO quiz_state(learner, pick_level, pick_kind)
VALUES(:learner, :level, '全部')
ON CONFLICT(learner) DO UPDATE SET
  pick_level = CASE WHEN pick_level = '全部' THEN :level ELSE pick_level END
