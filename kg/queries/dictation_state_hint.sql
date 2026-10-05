-- 看提示：当前词还没答时记下看过提示（交的时候 word_attempt.hinted 跟着记 1）。
UPDATE dictation_state
SET hinted = 1
WHERE learner = :learner AND current_word = CAST(:word AS INTEGER) AND answered = 0
