用包 common text code
# 读改测.zs —— 标准子脚本：读片段 → 问JSON 出改法 → 改文件 → 跑测试，失败原因和测试摘要带进下一轮。
# 参数：task（任务说明）、segs（要读的「文件:起-止」，多段逗号隔开不带空格）、rounds（默认 3，最多 5）、hint（可选）、first（可选）
# 返回：{outcome: 修好|没修好|无需改|缺原文, rounds, last:{msg, test}, reason, need, log}
# 缺原文：模型说要改却没给 edits（手里没有原文）时，用 need（「文件:起-止」或关键标识）在内部补读、多给一轮继续，
#         最多补读 2 次；补读不到新内容（或补读次数用完仍缺）才停，outcome=缺原文，need 里是缺的位置。
# first：定位.zs 里模型直接给的改法（{edits:[…]}）：开头直接改文件+跑测试（不调模型），过了就返回 修好；
#        没过就把改文件结果/测试摘要带进第 1 轮照常问。
设 n = {rounds 或 3}
设 hint = {hint 或 无}
设 done = 否
设 outcome = 没修好
设 used = 0
设 msg = 还没改过
设 reason = 无
设 need = 无
设 nbk = 0
设 log = 【读改测】
如果 {first.edits 或} 不为空
  设 res = 改文件 {first}
  设 msg = 【定位时直接给的改法】{res.msg}
  设 reason = {first.reason 或 无}
  设 t = 跑测试
  设 log = {log}｜第 0 轮（定位时直接给的改法，不调模型）：{res.msg}；测试通过={t.passed}
  如果 {t.passed} 等于 是
    设 done = 是
    设 outcome = 修好
  结束
否则
  设 t = 跑测试
结束
设 tsum = {t.summary}
遍历 i 于 1，2，3，4，5，6，7
  如果 {done} 等于 否 且 {i} 不大于 {n}
    设 used = {i}
    设 src = 读片段 {segs}
    问JSON r = 你在修一个 Python 项目（不能改测试文件）。任务：{task}｜提示：{hint}｜当前代码（每行带行号前缀「  12| 」，old 里不要带这个前缀）：{src}｜当前测试结果：{tsum}｜上一轮改文件的结果：{msg}｜如果上一轮改文件失败，按它说的原因改正（old 要和文件原文一字不差、含缩进、在文件里只出现一次）。代码已经没问题就 action 填 无需改；要改就给 edits，每项是一个对象，字段名固定为 file（相对项目根的路径，如 pkg/x.py）、old（原文）、new（替换后的文本）。要改的行不在上面的代码里（手里没有原文）就不要编 old：action 填 改、不给 edits、need 填缺的位置——「文件:起-止」，或能精确搜到那几行的关键标识（商品编号、函数名、带引号的字面量、文件名），系统会补读给你。 格式 action:改|无需改 reason:文本 edits?:列表 need?:文本
    设 reason = {r.reason}
    如果 {r.action} 等于 无需改
      设 done = 是
      设 outcome = 无需改
      设 log = {log}｜第 {i} 轮：模型说无需改：{r.reason}
    否则如果 {r.edits 或} 为空
      设 need = {r.need 或 无}
      如果 {nbk} 小于 2
        设 bk = 补读范围 {segs} {need} {reason}
        设 nbk = 计算 {nbk} + 1
      结束
      如果 {bk.added 或} 不为空 且 {segs} 不等于 {bk.segs}
        设 segs = {bk.segs}
        设 msg = 【第{i}轮】你说缺原文（need：{need}），{bk.note}，上面的代码已包含，请直接给 edits
        设 n = 计算 {n} + 1
        设 log = {log}｜第 {i} 轮：缺原文（need：{need}）→ {bk.note}，多给一轮
      否则
        设 done = 是
        设 outcome = 缺原文
        设 log = {log}｜第 {i} 轮：说要改但没给 edits，补读不到新内容，停下交回（need：{need}）：{r.reason}
      结束
    否则
      设 res = 改文件 {r}
      设 msg = 【第{i}轮改文件】{res.msg}
      设 t = 跑测试
      设 tsum = {t.summary}
      设 log = {log}｜第 {i} 轮：{res.msg}；测试通过={t.passed}
      如果 {t.passed} 等于 是
        设 done = 是
        设 outcome = 修好
      结束
    结束
  结束
结束
设 out = 组结果 {outcome} {used} {msg} {tsum} {reason} {log} {need}
返回 {out}
