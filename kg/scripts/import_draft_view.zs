# 教材导入编辑页：一课草稿的字段、现在的映射、可选的条目和知识点。由接口
# 「执行」，往响应里放 state.draft、lists（draft_maps、map_options）。
#
# 参数 draft：import_lesson 的 id；with_form：是 = 把字段填回表单（进页面、保存
# 之后），否 = 只清空加映射的两个框（加 / 去掉映射时，别把正在改、还没保存的
# 字段冲掉）。
#
# 表单里不放 draft 这个键：「载入」看到地址参数跟表单值一样就不拉了，而在
# 审阅页通过、驳回之后回到同一课，要重新拉才看得到新状态。

用包 db http common data

设 args.draft = {draft}
设 one = 查一行表 app.db import_draft_one {args}
如果 {one.draft 或} 为空
  设 missing.draft = {draft}
  设 missing.missing = 没有这一课草稿（{draft}），可能任务已经删了。
  设 missing.back = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5
  设 state.draft = {missing}
  响应 state {state}
  返回 missing
结束
设 one.missing = 
设 maps = 查询表 app.db import_draft_maps {args}
设 options = 查询 app.db import_map_options
设 group.draft_maps = {maps}
设 group.map_options = {options}
响应 lists {group}
设 state.draft = {one}
# 「保存了」由接口在这之后另放，这里先清掉上次的
设 state.draft_note = 
响应 state {state}
设 fields.map_add = 
设 fields.map_typed = 
如果 {with_form 或 否} 等于 是
  设 fields.title = {one.title}
  设 fields.draft_level = {one.draft_level 或}
  设 fields.seq = {one.seq 或}
  设 fields.summary = {one.summary}
  设 fields.explanation = {one.explanation}
  设 fields.formation = {one.formation}
  设 fields.examples = {one.examples}
结束
响应 form {fields}
