-- 交当前那个词的作答。只有「当前就是这个词、而且还没答过」时才改（影响 1 行）；
-- 同一个交第二次影响 0 行，调用方据此不再记作答——连按两下 Enter 不能算两次。
UPDATE dictation_state
SET answered = 1,
    dict_answer = NULLIF(:answer, ''),
    round_right = round_right + CAST(:correct AS INTEGER),
    round_total = round_total + 1
WHERE learner = :learner AND current_word = CAST(:word AS INTEGER) AND answered = 0
