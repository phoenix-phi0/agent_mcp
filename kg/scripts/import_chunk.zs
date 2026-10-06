# 教材导入：后台解析一块（routes/textbook_import.zs 用「后台执行」交过来，一块
# 一个，同时跑几个由引擎的后台线程池管，见 tools/dsl.py 的 _do_call_bg）。
#
# 参数 chunk：import_chunk 的 id。
#
#   1. 块标成解析中（次数加一）
#   2. 请模型（平衡档）从这块里抽出每一课：标题、等级、课序、一句话、讲解、
#      接续、例句，并从候选清单（已有的条目、知识点）里挑这课讲的
#   3. 草稿课写进 import_lesson（这块上次的草稿先删掉——重试就是重来），映射
#      过一遍存在性：库里没有的编号丢掉、记进 dropped（import_lesson_check），
#      绝不新建条目、知识点；再重算整个任务的问题提示
#   4. 块标成完成
#
# 模型出错（超时、排队太久……）脚本在「问」那一行就抛了：引擎接住，带着 error
# 跑 scripts/import_chunk_fail.zs 把块标成出错。模型回了话但不是要的 JSON，在
# 这里判，同样标出错，页面上能重试这一块。
#
# 改写开关（任务的 rewrite，默认开）：商业教材的原文不能直接入库，让模型用
# 自己的话写讲解和例句，只保留语法点名称、课序、等级这类事实。

用包 common db text data

设 args.chunk = {chunk}
设 affected = 写库表 app.db import_chunk_start {args}
设 one = 查一行表 app.db import_chunk_one {args}

设 cand_args.level_hint = {one.level_hint}
设 candidates = 查一值表 app.db import_candidates {cand_args}

设 style = 讲解、例句可以参照原文来写，例句可以沿用原文的。
如果 {one.rewrite} 等于 1
  设 style = 版权要求：这是商业教材，原文不能入库。title 只写语法点的名称（比如「〜てから」），summary、explanation、formation、examples 一律用你自己的话重新写：不要照抄原文的句子，也不要只改几个字搬运原文；例句自己造（每课 2 到 4 句，日语加中文翻译），不要用原文的例句。只有语法点名称、课序、等级这类事实可以照原文。
结束

系统 你是日语教材编辑，给中国的日语学习者整理语法课。你只根据给你的教材片段工作，不编造片段里没有的语法点。输出严格的 JSON。

问 raw = 下面是一本日语教材里的一段（第{one.seq}块，块标题「{one.title}」）。【教材片段开始】{one.body}【教材片段结束】请找出这段里讲的每一课（一个语法点或一组紧密相关的语法点算一课；片段只是目录、前言、练习答案这类没有讲语法的，就返回空列表）。对每一课给出：seq（课序，整数，按原文的第几课；看不出来就按出现顺序从 {one.seq} 开始数）、title、level（JLPT 等级 N5 到 N1，按语法点的常见等级判断）、summary（一句话说这课讲什么）、explanation（中文讲解，讲清意思、用法、注意点，200 到 500 字）、formation（接续，比如「动词て形 + から」，没有就空串）、examples（例句数组，每项是有 jp 和 zh 两个键的对象）。{style} 然后把这课映射到网站上已有的语法条目和知识点：只能从下面的候选清单里挑编号，清单里没有合适的就不挑，绝对不要自己编编号。items 是这课讲的条目编号（「条目」开头那几行的第一个字段，数组，最相关的在前），points 是这课讲的知识点编号（「知识点」开头的行；对不上具体条目、只知道属于哪个知识点时用），confidence 是你对映射的把握（0 到 1 的小数），reason 是一句话说为什么这样映射。【候选清单开始】{candidates}【候选清单结束】只输出一个 JSON 对象，唯一的键是 lessons，值是数组，每课一个对象；每个对象必须有这 11 个键，一个都不能少：seq、title、level、summary、explanation、formation、examples、items、points、confidence、reason（items、points 没有合适的就写空数组，不要省略这两个键）。不要别的文字。 用 平衡

设 parsed = 解析JSON {raw}
设 key_n = 条数 {parsed}
如果 {key_n} 等于 0
  设 fail.chunk = {chunk}
  设 fail.error = 模型的回复不是要的JSON（解析不了），可以重试这一块
  设 affected = 写库表 app.db import_chunk_fail {fail}
  返回 bad_json
结束
设 lessons = {parsed.lessons 或}
设 lesson_n = 条数 {lessons}

事务 app.db
  设 affected = 写库表 app.db import_lesson_clear_chunk {args}
  如果 {lesson_n} 大于 0
    遍历 lesson 于 {lessons} 序号 i
      设 row.job = {one.job}
      设 row.chunk = {chunk}
      设 row.chunk_seq = {one.seq}
      设 row.seq = {lesson.seq 或}
      设 row.title = {lesson.title 或}
      设 row.level = {lesson.level 或}
      设 row.summary = {lesson.summary 或}
      设 row.explanation = {lesson.explanation 或}
      设 row.formation = {lesson.formation 或}
      设 row.examples = {lesson.examples 或}
      设 row.items = {lesson.items 或}
      设 row.points = {lesson.points 或}
      设 row.confidence = {lesson.confidence 或}
      设 row.reason = {lesson.reason 或}
      设 affected = 写库表 app.db import_lesson_insert {row}
    结束
  结束
  # 存在性：库里没有的编号丢掉、记下来；再重算整个任务的问题提示
  设 affected = 写库表 app.db import_lesson_check {args}
  设 job_args.job = {one.job}
  设 affected = 写库表 app.db import_issues {job_args}
  设 done.chunk = {chunk}
  设 done.note = 
  如果 {lesson_n} 等于 0
    设 done.note = 这块没认出课（目录、前言、练习之类），不用管；觉得不对可以重试
  结束
  设 affected = 写库表 app.db import_chunk_done {done}
结束
返回 ok
