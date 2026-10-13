用包 common text code
# 定位.zs —— 现场决策找代码：搜索 {kw} → 问JSON 选 换关键词|读这些|运行看看|改 → 换关键词就再搜，运行看看就跑代码把输出带进下一轮，读这些就读片段并返回。
# 读这些 之前先 核对范围——从 reason/运行输出（搜索被截断时再加任务描述）里抽关键标识，不在要读的范围里就精确搜索补读「行号 ±25」并在 note 里注明；
# 运行看看 的限制写进提示，被拒时把拒绝原因带进下一轮。
# 规则、动作说明、输出格式这些固定说明在系统提示里（prompts.LIB_SYSTEM，提示以【定位】开头时 AgentEngine 自动换上），这里只放变化内容，好命中缓存。
# 直连——可选参数 pre（预读段落「文件:起-止,…」）：开头先读进来放进每轮提示；模型已经看得到要改的原文时可以选「改」直接给 edits，
# 这时不再单独「读」，返回 first={edits…}，读改测.zs 第一轮直接应用、不再问模型。
# 参数：task（任务说明）、kw（起始关键词，正则，空格写 \s）、hint（可选）、rounds（默认 3，最多 5）、pre（可选）
# 返回：{outcome: 找到|没找到, segs, src, note, kw, rounds, log, first}；找到时 segs 是要改的「文件:起-止」，src 是读到的原文，note 是模型的判断，first 是模型直接给的改法（没有就空）
设 n = {rounds 或 3}
设 hint = {hint 或 无}
设 pre = {pre 或 无}
设 done = 否
设 outcome = 没找到
设 segs = 无
设 src = 无
设 note = 无
设 used = 0
设 first = 无
设 runout = 还没运行过
设 hist = 无
设 log = 【定位】
设 presrc = 无预读
如果 {pre} 不等于 无
  设 presrc = 读片段 {pre}
结束
遍历 i 于 1，2，3，4，5
  如果 {done} 等于 否 且 {i} 不大于 {n}
    设 used = {i}
    设 hits = 搜索代码 {kw}
    设 last = 提示：还有轮次，可以换关键词或运行看看
    如果 {i} 等于 {n}
      设 last = 提示：这是最后一轮，能确定就给 读这些 或 改
    结束
    问JSON d = 【定位】你在帮忙定位并修一个 Python 项目里的问题（不能改测试文件），规则和输出格式见系统提示「定位」一节。任务：{task}｜线索：{hint}｜第 {i}/{n} 轮，{last}｜前几轮：{hist}｜已预读的原文（每行带行号前缀「  12| 」）：{presrc}｜本轮搜索正则 {kw} 的结果（每行「文件:行号: 那一行」；命中超过 30 条时开头有总数、按文件的命中数，末尾有换关键词提示）：{hits}｜上一次运行看看的输出：{runout} 格式 action:改|换关键词|读这些|运行看看 kw?:文本 segs?:文本 code?:文本 edits?:列表 reason:文本
    设 hs = 截取 {hits} 1 300
    设 hist = {hist}｜第{i}轮 搜 {kw} → {hs} → {d.action}：{d.reason}
    设 note = {d.reason}
    如果 {d.action} 等于 改 且 {d.edits 或} 不为空
      设 segs = 合并段落 {pre} {d}
      设 first = {d}
      设 src = {presrc}
      设 done = 是
      设 outcome = 找到
      设 log = {log}｜第 {i} 轮：直接给改法（{segs}）：{d.reason}
    否则如果 {d.action} 等于 读这些 且 {d.segs 或} 不为空
      设 clue = {d.reason}｜{runout}
      设 ck = 核对范围 {d.segs} {clue} {hits} {task}
      设 segs = {ck.segs}
      如果 {ck.added} 不为空
        设 note = {d.reason}｜{ck.note}
        设 log = {log}｜第 {i} 轮：核对范围（搜索截断={ck.trunc}，标识 {ck.ids}）：{ck.note}
      结束
      设 src = 读片段 {segs}
      设 done = 是
      设 outcome = 找到
      设 log = {log}｜第 {i} 轮：读这些 {segs}：{d.reason}
    否则如果 {d.action} 等于 运行看看 且 {d.code 或} 不为空
      设 ran = 运行代码 {d.code}
      设 runout = 【第{i}轮运行】{ran.text}
      如果 {ran.ran} 等于 否
        设 runout = 【第{i}轮运行被拒，没跑】{ran.text}｜下次运行看看只 import 项目里的模块打印中间值，别用 subprocess/os.system/socket，别跑测试
      结束
      设 rs = 截取 {ran.text} 1 300
      设 log = {log}｜第 {i} 轮：运行看看：{rs}
      如果 {d.kw 或} 不为空
        设 kw = {d.kw}
      结束
    否则
      如果 {d.kw 或} 不为空
        设 kw = {d.kw}
      结束
      设 log = {log}｜第 {i} 轮：{d.action} → {kw}：{d.reason}
    结束
  结束
结束
设 out = 组定位 {outcome} {segs} {src} {note} {kw} {used} {log} {first}
返回 {out}
