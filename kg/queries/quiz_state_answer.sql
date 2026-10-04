-- 交上一道题的作答。只有「当前就是这道、而且还没答过」时才改（影响 1 行）；
-- 同一道交第二次影响 0 行，调用方据此不再记学习记录——连点两下不能算两题。
UPDATE quiz_state
SET answered = 1,
    choice = NULLIF(:choice, ''),
    given = NULLIF(:given, ''),
    right = right + CAST(:correct AS INTEGER),
    total = total + 1
WHERE learner = :learner AND current = :code AND answered = 0
