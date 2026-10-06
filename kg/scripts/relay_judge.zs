# 传达判定：一条带了传达的老师回复成功生成后，routes/teacher.zs 用「后台执行」交过来
# （学生不等它）。用「快」档模型判这条回复有没有把要点传达到、必须准确的信息说对
# 没有、摘出实际传达的那句话，结论写回 relay_use 和 relay_state。
#
# 参数 use_id：relay_use 的 id（哪条回复带了哪条传达）。
#
# 结论（queries/relay_verdict.sql 把模型回的 JSON 归成一个）：
#   已传达    状态已传达，记那条回复、摘录、时间，以后不再带入
#   有误      第一次标「传达有误」，下一条回复再带一次并要求更正；第二次「有误已停止」
#   未传达    没传达到的次数加一，到轮数阈值升级为立即
#   判定失败  模型回了 JSON 但没有 delivered：当未传达算，理由里写明
# 模型出错、回的不是 JSON（问JSON 解析不了就抛）：引擎带着 error 跑
# scripts/relay_judge_fail.zs，同样当未传达算、记下原因。都不影响学生已经拿到的回复。
#
# 传达后来被删了、回复找不到：什么也不做，不调模型。

用包 common db

设 args.use_id = {use_id}
设 one = 查一行表 app.db relay_judge_load {args}
如果 {one.use_id 或} 为空
  返回 gone
结束
设 facts = {one.relay_facts 或 （没有）}

系统 你是日语学习网站的传达检查员。任课老师让 AI 老师在给学生的回复里转达一件事，你判断这条回复有没有转达到。你只输出一个 JSON 对象，不加任何解释。
问JSON judged = 老师要转达给学生的要点：【{one.relay_point}】必须准确的信息：【{facts}】AI 老师给学生的回复：【{one.reply}】请判断：学生只读这条回复，能不能明白老师要转达的要点（意思到了就算，不要求原话；只是沾边、含糊带过、只说了一半都不算）。输出一个 JSON 对象，键：delivered（是 或 否）；accurate（回复里涉及「必须准确的信息」的地方是否和给的完全一致，是 或 否；没给必须准确的信息、或者根本没转达，写 无）；quote（回复里实际转达这件事的那一两句原文，照抄，没转达写空串）；reason（一句话说理由，说错了的话写清哪里不对、正确的是什么）。 用 快

设 judge.use_id = {use_id}
设 judge.delivered = {judged.delivered 或}
设 judge.accurate = {judged.accurate 或}
设 judge.facts = {one.relay_facts 或}
设 judge.quote = {judged.quote 或}
设 judge.reason = {judged.reason 或}
设 judge.verdict = 查一值表 app.db relay_verdict {judge}
如果 {judge.verdict} 等于 判定失败
  设 judge.reason = 判定模型回的JSON里没有delivered（是/否），当没传达到算
结束
如果 {judge.verdict} 等于 未传达
  设 judge.quote =
结束

事务 app.db
  设 affected = 写库表 app.db relay_use_judge {judge}
  设 affected = 写库表 app.db relay_state_judge {judge}
结束
返回 {judge.verdict}
