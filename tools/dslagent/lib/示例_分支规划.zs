用包 common text code
预算 调用 10 秒 600
# 示例（src 可选，fast / slow 是秒）：测导入耗时 → 按耗时三路分支 → 先套脚本末尾写好的 #改法 e1 → 没成再派任务 → 套改法跑测试 → 重试或终止
设 mod = {mod 或 pkg}
设 src = {src 或 无}
设 fast = {fast 或 0.5}
设 slow = {slow 或 3}

# 一、命令：测导入耗时
设 code = t0=0;import time;t0=time.time();import {mod};print('SEC=%.3f'%(time.time()-t0))
设 rc = 运行代码 {code}
设 m = 匹配 {rc.text} SEC=([0-9.]+)
如果 {rc.ran} 不等于 是 或 {m.matched} 不等于 是
  终止 失败 导入 {mod} 跑不起来：{rc.text}
结束
设 sec = {m.groups.0}

# 子任务入参：耗时、谁在导入它、源码
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
  设 rs = 并行派任务 {jobs} 2
  设 inp.findings = {rs}
  设 desc = 导入{mod}太慢（{sec}秒），结合入参里的 findings 给出懒加载改法
否则
  设 desc = 导入{mod}偏慢（{sec}秒），给出懒加载改法
结束

# 三、先套 #改法 e1（原文看得到时直接写死，不调模型）；没套上或测试没过，把原因带进下面的派任务
设 last = 无
设 res = 改文件 {e1}
如果 {res.ok} 等于 是
  设 t = 跑测试
  如果 {t.passed} 等于 是
    终止 成功 计划里写好的改法套上、测试通过：{res.msg}
  结束
  设 last = 计划里写好的改法套上了但测试没过：{t.summary}
否则
  设 last = 计划里写好的改法没套上：{res.msg}
结束

# 四、派任务 → 套改法 → 跑测试；不行带原因重试，用完终止
设 n = 0
当 {n} 小于 2 最多 5 次
  设 n = 计算 {n} + 1
  设 inp.last = {last}
  设 r = 派任务 {desc} {inp} {logic} edits:列表,note:文本
  如果 {r.status} 等于 超出预期
    终止 超出预期 子任务说前提不对：{r.reason}
  否则如果 {r.status} 等于 失败
    设 last = 第{n}次派任务失败：{r.reason}
    继续
  结束
  设 res = 改文件 {r.result}
  如果 {res.ok} 不等于 是
    设 last = 第{n}次改法没套上：{res.msg}
    继续
  结束
  设 t = 跑测试
  如果 {t.passed} 等于 是
    终止 成功 第 {n} 次改法通过测试：{r.result.note}
  结束
  设 last = 第{n}次改了但测试没过：{t.summary}
结束
终止 失败 试了 {n} 次没成：{last}

#改法 e1
@@ 改 pkg/loader.py
<<<<<<< 原文
import yaml


def load(path):
    with open(path, encoding="utf-8") as f:
=======
def load(path):
    import yaml
    with open(path, encoding="utf-8") as f:
>>>>>>> 新文

#清单
改 pkg/loader.py:load
