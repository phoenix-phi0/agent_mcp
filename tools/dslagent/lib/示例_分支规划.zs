用包 common text code
# 示例_分支规划.zs —— 分支式规划的写法示例：测导入耗时 → 按耗时三路分支 → 派任务要改法 → 套改法跑测试 → 按结果重试或终止。
# 每一步是 命令（运行代码 / 跑测试）、直接改法（改文件）或子任务（派任务 / 并行派任务）；任何一步都能 终止 整个流程。
# 参数：mod（要测的模块，默认 pkg）、src（要附给子任务的源码，「文件:起-止」，可选）、fast（秒，低于它不用改，默认 0.5）、
#       slow（秒，高于它先并行查原因，默认 3）、tries（改法最多试几次，默认 2）
# 结果：终止 成功|失败|超出预期 原因。被 执行 调用时调用方拿到 {状态, 原因, 停在}。
# 空跑（plan.dry_run）时 派任务 / 并行派任务 不调模型，给结构合法的假结果。
设 mod = {mod 或 pkg}
设 src = {src 或 无}
设 fast = {fast 或 0.5}
设 slow = {slow 或 3}
设 tries = {tries 或 2}

# 一、命令：测导入耗时
设 code = t0=0;import time;t0=time.time();import {mod};print('SEC=%.3f'%(time.time()-t0))
设 rc = 运行代码 {code}
设 m = 匹配 {rc.text} SEC=([0-9.]+)
如果 {rc.ran} 不等于 是 或 {m.matched} 不等于 是
  终止 失败 导入 {mod} 跑不起来：{rc.text}
结束
设 sec = {m.groups.0}
打印 导入 {mod} 用了 {sec} 秒

# 子任务的入参：耗时、谁在导入它、源码（文件:起-止 由 派任务 读出那几行附上）
设 refs = 查引用 {mod} py
设 inp.timing = 导入{mod}用了{sec}秒
设 inp.users = {refs.text}
如果 {src} 不等于 无
  设 inp.src = {src}
结束
设 logic = 要求：把导入时最耗时的模块级导入改成在用到它的函数里再导入（懒加载），行为不变；不改测试文件；edits 每项字段名固定为 file、old、new，old 从入参原文一字不差抄、不带行号前缀

# 二、三路分支
如果 {sec} 小于 {fast}
  终止 成功 导入只用 {sec} 秒，低于 {fast} 秒，不用改
否则如果 {sec} 大于 {slow}
  # 很慢：先并行查两个互不依赖的方向，发现带进改法
  设 jobs = 解析JSON []
  设 job.任务 = 任务：列出{mod}导入链里最耗时的第三方库
  设 job.入参 = {inp}
  设 jobs = 列表加项 {jobs} {job}
  设 job.任务 = 任务：列出{mod}里导入时就执行的重计算（模块级的读文件、建表、编译正则）
  设 jobs = 列表加项 {jobs} {job}
  设 rs = 并行派任务 {jobs} 2
  遍历 f 于 {rs}
    打印 并行查：{f.状态} {f.结果}
  结束
  设 inp.findings = {rs}
  设 desc = 导入{mod}太慢（{sec}秒），结合入参里的 findings 给出懒加载改法
否则
  设 desc = 导入{mod}偏慢（{sec}秒），给出懒加载改法
结束

# 三、派任务 → 套改法 → 跑测试；不行带着原因重试，用完次数终止
设 n = 0
设 last = 无
当 {n} 小于 {tries} 最多 5 次
  设 n = 计算 {n} + 1
  设 inp.last = {last}
  设 r = 派任务 {desc} {inp} {logic} edits:列表,note:文本
  打印 第 {n} 次派任务：{r.状态} {r.原因 或}
  如果 {r.状态} 等于 超出预期
    终止 超出预期 子任务说前提不对：{r.原因}
  否则如果 {r.状态} 等于 失败
    设 last = 第{n}次派任务失败：{r.原因}
    继续
  结束
  设 res = 改文件 {r.结果}
  如果 {res.ok} 不等于 是
    设 last = 第{n}次改法没套上：{res.msg}
    继续
  结束
  设 t = 跑测试
  如果 {t.passed} 等于 是
    终止 成功 第 {n} 次改法通过测试：{r.结果.note}
  结束
  设 last = 第{n}次改了但测试没过：{t.summary}
结束
终止 失败 试了 {n} 次没成：{last}
