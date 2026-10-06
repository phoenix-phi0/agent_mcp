-- 一课草稿通过或驳回（:review 只认这两个）。
UPDATE import_lesson SET review = :review
WHERE id = CAST(:draft AS INTEGER) AND :review IN ('通过', '驳回', '待审')
