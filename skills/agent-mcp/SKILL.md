---
name: agent-mcp
description: 用 agent_mcp 这个自建 MCP 开发中文 DSL 项目（.zs 接口脚本、.ui 界面、.entity 建模）、gen 代码生成器、知识图谱和单词库。凡是涉及这个项目的改代码、加接口、加界面、加实体、跑测试、导入导出数据、排查「不报错但行为不对」的问题，都先看这个技能——它记录了工具的基准目录、验证流程，以及一批只会静默失败、光看代码发现不了的坑。
---

# agent_mcp 项目的用法

项目在 WSL 的 `/home/ysc/mcp`。引擎是一套中文 DSL：`.zs` 写接口、`.ui` 写
界面、`.entity` 建模，`gen` 按实体生成整套增删改查。

## 一、工具和基准目录

**基准目录不一样，混用会改错文件**（踩过，症状是「改了没生效」）：

| 工具 | 基准 | 用途 |
|---|---|---|
| `mcp_read` / `mcp_write` / `mcp_edit` / `mcp_ls` | 项目根 | 改代码，**默认用这套** |
| `file.edit` / `file.show` | `data/` | 早期遗留，基本不用 |

`mcp_edit` 是精确替换，`old` 必须唯一匹配。**往几百行的文件中间插代码时，
锚点要选得足够独特**——我有三次匹配到了错误的位置：删掉了函数定义行、把新
代码插进了另一个函数体、把一个函数改成了调用自己（无限递归）。**改完立刻
`mcp_read` 或 `sed -n` 看一眼实际结果**，不要假设改对了。

## 二、跑命令用 ZBatch，不要用 dsl_run

```
zbatch.submit  tasks=["在 WSL 里跑这段，把输出原样贴出来（报错贴全）：..."]
zbatch.wait    job_id=... timeout=110 every=15
zbatch.status  job_id=... full=true      # wait 的输出会被截断，要全文用这个
```

**为什么不用 `dsl_run`**：MCP 进程里缓存着动词包的模块，改完包再跑还是旧的。
ZBatch 每次是新进程。验证引擎改动一律用它。

**提示词里要写明**「不要改任何文件」「测试失败就如实贴出，不要改测试脚本」——
否则执行端可能自作主张改东西。

ZBatch 服务没开时，用 CBatch 代替：参数和用法一样，执行端是本机的 `claude -p`，
不用起服务。

```
cbatch.submit  tasks=[...] cwd="/home/ysc/mcp"      # 默认 sonnet，要别的传 model
cbatch.submit  tasks=[...] model="auto"             # haiku 先按难度给每条分 haiku/sonnet/opus
cbatch.wait    job_id=... timeout=110 every=15
```

默认不放开权限：需要批准的工具调用会被直接拒掉，被拒的工具记在任务的 `denied`
字段里。要让它改文件就传 `permission_mode="acceptEdits"`，或者用 `allowed_tools`
指定具体工具。`bypassPermissions` 不收。

**执行方式 `engine`**（job 级参数，tasks 里的字典可逐条覆盖）：

- `claude`（默认）：上面说的 claude -p，行为完全不变。
- `dsl`：交给 `tools/dslagent`（中文 DSL 修 bug 流程：固定模板一版 → 没修好再让模型写 .zs 计划，最多 2 版），
  **在 `project` 目录里直接改文件**。字段：`project`（必填，规则同 cwd）、`test_cmd`（可选，缺省按项目探测
  pytest / unittest）、`fallback`（默认 true：dsl 没修好就交 claude -p 兜底，cwd=project，提示词带上 dsl 的
  交接说明和 diff；权限沿用这批的 permission_mode / allowed_tools，都没给就是 acceptEdits + 只放行测试命令）。
- `auto`：执行时判定——给了 project，且（给了 test_cmd 或提示词里有「失败的测试」/Traceback/AssertionError 之类），
  且测试能跑、初始确实有失败 → dsl；否则 → claude。理由记在任务的 `engine_reason`。

```
cbatch.submit  engine="dsl" tasks=[{"prompt": "用户报告…失败的测试：tests.test_x…", "project": "/home/ysc/proj"}]
cbatch.submit  engine="auto" project="/home/ysc/proj" tasks=["…Traceback…", "给 README 加一节"]
```

每条任务多记 `engine_used`（template / plan / claude_fallback / claude）、`versions`、`calls`、`cost_usd`、
`seconds`、`calls_log`（任务目录 `task_<n>/calls.json`，同目录有每版的 .zs、打印输出、result.json）。
**适用范围**：只在「项目有测试、要让失败的测试通过」的修 bug 任务上验证过（shopkit N1–N10，回归 10/10）；
**限制**：dsl 只有 code 动词包的能力——读/搜 .py、精确替换改文件、跑测试、跑 ≤30 行只读 Python，
不能装依赖、不能改测试、不能跑别的命令；不像修 bug 的活别用 dsl。dsl 在独立进程里跑（`python -m tools.dslagent run`），
临时目录默认 `~/.cache/dslagent/tmp`（`DSLAGENT_TMP` 可改），不用 /tmp。改了 cbatch.py 后 `tool_call … reset=True`
就能让 submit 认新参数（执行器每批都是新进程，本来就用磁盘上的新代码），不用重启 zmcp。
真模型集成测试：`tests/tools/dslagent_live.py paths|regress`（手动跑，花钱）。
**首 token 对冲**（`tools/dslagent/pool.py`）：一次模型调用发出 7 秒还没出首 token，就现起一个同系统提示+模型的
备用 claude 进程重发同一问题，谁先出首 token 用谁、另一路直接杀掉（备用赢了就接替成常驻进程）；每次调用最多对冲 1 次，
总超时（`DSL_CLAUDE_TIMEOUT`，默认 150）仍从主路发出算。阈值依据：plan9/11/12 共 344 次调用，正常首 token 最大 5.98 秒、
长尾从 8.3 秒起（6.4%，最长 72 秒，另有 150 秒超时）。`DSLAGENT_HEDGE_SEC` 改阈值，`0` 关掉。备用不预热
（每个 claude 进程约 290MB，并发 3 时全预热要多占 ~1.7G）。calls.json 每次调用记 `hedged`、`winner`（primary/backup）、
`hedge_at_ms`、`extra_cost`（被杀那一路按 message_start 的 usage 估，已计入 `cost`；没出 message_start 记 0）。
**卡流对冲**：出了首 token（thinking 增量也算）之后这一路 20 秒没有任何新行，也现起备用重发，卡住那路不杀、谁先给出
完整结果用谁（`DSLAGENT_STALL_SEC`，`0` 关）。plan15 B7、plan16 B4 那两次「150 秒超时、hedged=False」就是首 token
7 秒内出了、之后流卡死；旧记录超时不带 ttft，看着像没出首 token。现在超时/崩溃的调用也记 `ttft_ms`、`hedge_reason`
（no_token/stall）、`first_out_ms`、`no_output_ms`、`stall_ms`、`legs`（每一路的时刻明细）。问题在后台线程里写 stdin，
进程还在启动、没读 stdin 时计时照样从发出算。
**推理候选补充预读**（`tools/dslagent/infer.py`，默认开）：模板抽参之后，用 ast 抽项目事实（调用/同名方法弱边/常量读取/
字面量/舍入/读 json）+ 小 Datalog 求值（从失败测试出发的调用闭包、名字/traceback/数据命中）+ 打分，取前 K=8 段**合并**进
第一次定位的预读：模板预读不动，被同文件已有段包住的跳过，按名次加、加上会超 675 行（模板上限 450 的 1.5 倍）的跳过；
不替代模板、不做硬过滤，只是多给模型几段原文。抽事实在开局跑测试时后台先做；抽取/推理出错、等待超过 3 秒
（`DSLAGENT_INFER_TIMEOUT`）、.py 超过 400 个 → 回退为只用模板预读。result.json 的 `infer`（及第 1 版 `template.infer`）
记本地耗时、候选段、模板原预读、合并后预读、`fallback`（回退原因，空＝没回退）。关：`DSLAGENT_INFER=0` 或
`python -m tools.dslagent run --no-infer`。规则/权重/段长与 plan15 冻结版逐项一致（`tests/tools/test_dslagent_infer.py`
在实验场景存在时对照）。实测（各 1 次）：N1–N10 10/10、B1–B8 8/8，首次定位直接给改法 N 7/10（原 3/10）、B 5/8（原 0/8），
本地耗时均 ≈0.35 秒。**局限**：项目小时模板本就整份预读，候选几乎不增量（≤60 行的文件整份给，偏差在预读量而非位置）；
读错字典键、大差额的舍入错（只认断言两边差 ≤2 的舍入）没有专门规则；动态调用（getattr、字典分派、obj.m()）
只按同名方法尽力连边，只作排序提示；同分的段先后随 hash 种子变（段集合不变）。

GBatch 接口同 CBatch，执行端换成 Grok Build 的 `grok -p`（`gbatch.submit/wait/
status/...`，`gbatch.describe()` 列出权限用法和工具名映射）。跟 CBatch 的差别：

- **要批准的调用会让整条中断**（stopReason=cancelled，退出码照样 0），不是只拒
  那一个接着干。被中断记 error，写明卡在哪个调用（「需要批准：Edit /tmp/x.py」），
  status/wait 的 `hint` 给出该加的 `allowed_tools`。
- `permission_mode="acceptEdits"` 在 grok 里本身不生效（运行时没有这个模式，落到
  default），gbatch 自动补 `--allow Edit`；**跑命令还要 `allowed_tools` 加 `Bash`
  或 `Bash(python3 *)` 这类**。只给 Bash 不算能写文件（模型会用 write 工具）。
  **带重定向的串联命令连 `--allow Bash` 也盖不住**（实测 `mkdir && printf … > a.py
  && python3 a.py` 被中断），提示词里写明「用写文件工具建文件、命令一条一条跑」。
  命令前加环境变量赋值（`PYTHONPATH=… python3 x.py`）同样被拦，`--rules` 已叮嘱
  模型改用 `sys.path.insert` 或先 cd / 用绝对路径。
- `allowed_tools` 收 Claude 的名字，自动翻：Glob→Grep、Write/MultiEdit/
  NotebookEdit→Edit、LS→Read；`Bash(...)` 这类原样；认不出的（Task 等）跳过、
  进返回值和 job.json 的 `warnings`。`"*"` 不收。
- **推理强度 `effort`**（→ `--reasoning-effort`）：`low` / `medium` / `high` / `xhigh`，
  也收 低/中/高/极高，默认 `medium`；`None` 或空串不传，用 CLI 自己的默认（high）。
  非法值 submit 时直接报错；`grok-4.5*` 模型不支持 `xhigh`。tasks 里的字典可单条覆盖：
  `{"prompt": "...", "effort": "low"}`，优先于 job 级。实际用的值在 job.json 的
  `options.effort` 和每条的 `cmd`。分档：轻任务（查文件、列清单、简单函数）用 `low`；
  一般用默认 `medium`；复杂排查/重构用 `high`；`xhigh` 只给确实需要的难题。
- submit 返回的 `warnings` 还有预检：提示词像要写文件/跑命令而没放行时提醒。
- 模型默认用 grok 自己的，没有 `model="auto"`；原始输出在任务目录
  `task_<n>.raw.json` / `task_<n>.stderr.log`，实际命令行在 job.json 的 `cmd`。

**清理起的服务不要用 `pkill -f '关键字'`**：它会匹配到跑这段脚本的 shell 自己，
把自己杀掉（犯过三次）。记 PID 按进程组杀：

```bash
(setsid cmd > /tmp/x.log 2>&1 & echo $! > /tmp/x.pid)
kill -TERM -"$(cat /tmp/x.pid)"
```

**kg 的 8197 服务是用户级 systemd 服务 `kg8197`**（unit 在 `~/.config/systemd/user/kg8197.service`，
不进仓库；已开 linger，独立于 zmcp.service 的 cgroup）。重启用
`systemctl --user restart kg8197`，状态 `systemctl --user status kg8197`，
日志 `/tmp/kg_8197.log`。**不要再用 setsid 起 8197，也不要按进程组 kill**
（会被 systemd 拉起来重启，或者和它打架）。上面的 setsid + 按组杀只适用于临时起的服务。
命令行里没有 `XDG_RUNTIME_DIR` 时先 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`。

服务的日志写文件，不要接管道——Flask 每请求一行日志，几百个请求就把 64KB
的管道缓冲区写满，服务卡死，看着像挂了。

## 三、验证流程

```bash
bash /home/ysc/mcp/tests/run_all.sh      # 全部测试，约 90 秒
```

17 组、460 项。改引擎、改模板、改生成器之后**必须跑**，因为一处改动常常影响
所有生成的项目。

**只验证到接口层不算数。** 这个项目里「接口返回正确」和「页面上是对的」反复
不一致：勾选框把库里的 1 显示成没勾、保存成功没有任何提示、浮层保存后不关、
编辑时改主键会改错另一条记录——全是接口测试发现不了、浏览器测试一跑就现形
的。浏览器测试在 `tests/e2e/*.js`：起真服务、用 jsdom 加载真实生成的页面、
`fetch` 打到真服务，按人的操作顺序点。新功能照着现成的写。

**测试里要有对照。** 写「伪造的令牌被拒」这类断言时，先写一条「正确的能用」。
有一次 cookie 根本没送到服务器，四条「被拒」全是白过的，是对照那条失败才
暴露的。

## 四、DSL 的坑

**语句和动词是两回事。** `读JSONL` 是语句：

```
读JSONL rows = content/kg.jsonl     ✓
设 rows = 读JSONL content/kg.jsonl  ✗ 整行被当成文本存进变量
```

后者现在会报错（专门加的检查），但同类问题要警惕。

**动词参数按空格切**，值里有空格就错位且不报错。收整个字典的版本：

```
查询表 / 查一行表 / 查一值表 / 写库表    库 查询名 {request}
```

用户输入（标题、搜索词、日语例句）一律用这些，不要用按位置传的。

**条件、分支、算术**：

```
如果 {a} 等于 1 且 ( {b} 包含 x 或 非 {c} 为空 )     非 > 且 > 或，短路，括号半角全角
  …
否则如果 {a} 等于 2                                  可以多个；「否则 如果」同义
  …
否则
  …
结束
设 total = 计算 {a} * 2 + 1                          + - * / // % 取整 四舍五入(x,2) 最大 最小 绝对值
```

**循环**（遍历之外）：

```
当 {done} 不等于 是 且 {n} 小于 5 最多 6 次      条件同「如果」，每轮开头重新求值；「最多 N 次」必写
  …                                              （N 1–1000 或 {变量}）。跑满仍成立不报错，往下走，
结束                                             {loop_full}=是（正常结束=否），trace 记一条
重复 3 次 计数 i                                 固定次数（0–1000），计数从 1 开始，可省
  如果 {i} 等于 2
    继续                                         跳到最内层循环下一轮；「跳出」结束最内层循环
  结束
结束
```

跳出/继续 在 当/重复/遍历/逐项 里都能用，嵌套只管最内层；写在循环外（子脚本里没套循环也算）
**运行之前**就报「第 N 行：…只能写在循环里面」，空跑能查出来。事务里跳出＝正常结束（提交）；
「返回」照旧结束整个脚本。每轮迭代记在 `engine.trace`（不进输出；`python -m tools.dsl x.zs --trace`
打到 stderr）。示例：`tests/dsl/fixtures/loop_check.zs`（执行—检查—决定）。

「计算」是引擎关键字，不是动词：动词参数按空格切、拿到的是展开后的文本，带空格的
算式传不进去，而且值会被拼进算式（作答里写 `1) * 0 + (9` 就改了算式）。引擎在原文
里认 {变量}，每个值只当一个数，转不了就报错。除数是 0 报错，整数结果出整数。

正则：text 包的 `匹配`（→ {matched 是/否, all, groups, named}）、`找全部`（列表）、
`按正则切分`（列表，分组不夹进结果）、`替换`、`挑行`。正则写错直接抛。

**数值比较要 CAST。** 参数一律是字符串，`count(*) >= :n` 恒假且不报错，
要写 `CAST(:n AS INTEGER)`。

**慢活放后台**：`后台执行 scripts/x.zs k={v} on_error=scripts/x_fail.zs` 马上
返回，子脚本在后台线程池（同时最多 DSL_BG_WORKERS 个，默认 2）跑，结果自己写库、
页面轮询；出错时引擎带着 `error`（一句人话）跑 on_error 的脚本。**空值别当脚本
参数传**：`执行 a.zs job= review=x` 会把后面整段吞进 job，先设成 `-` 之类。测试里
`tools.dsl.wait_background()` 等它跑完。假模型（MockClient）也接「问JSON」：回复照常
按规则 / handler 出，当 JSON 解析，解析不了照样抛（跟真模型一样走 on_error）。

**「问JSON」加格式约束**：

```
问JSON r = 判断 {answer} 格式 action:合格|重做 reason:文本 score?:数字 重问 3 次 用 快
```

类型 `文本`（非空字符串）`数字`（能转数字的字符串转成数字存回）`是否`（是/否/true/false
→ 布尔，插值出 是/否）`列表` `A|B|C`（枚举，去首尾空白再比）；字段名后加 `?` 可选
（可选字段缺失、null、空串或纯空白都算「没给」：不算错，结果里去掉这个键，`{r.x}` 跟缺失一样；
必填文本空串照旧算错），多余字段不管，只查顶层，回的不是对象算错。引擎自动在提示词末尾附格式说明和示例 JSON。
不对（含非法 JSON）就把具体问题（「action 只能是 合格 或 重做，你回了 基本合格；缺少字段
reason」）连同它上次的回复发回去重问，默认 2 次（`重问 N 次`，0–5）；用完抛「第 N 行：
问JSON 格式不对：…；最后一次回复：…」，脚本停（接口 500）。顺序 `附 → 格式 → [重问] → 用`
（「附」写在格式后面也认）；「格式」只在末尾、后面每个词都是 `名字:类型` 时才认，否则是
提示词正文；类型写错直接报错。不带「格式」的旧写法完全不变（不附说明、CLI 不重试）。
**流程控制里的模型判断，用 问JSON 加格式，再用 如果 判字段**（`如果 {r.action} 等于 重做`）。
假模型测重问用 `MockClient(replies=[…], offline=True)` 按顺序回。

**出错一律抛。** db 包的查询和写库出错时抛异常，不返回错误值——早先返回
`[{"错误": …}]`，看起来就是一行数据，页面上多一行空白，人看不到报错。

**约束冲突会被翻译成人话**：重名回 409「标题已经存在」，必填为空回 400，
字段名取自 `.entity` 的标签。这是在 `tools/db_errors.py`。

## 五、.ui 的约束

**嵌套规则**：`分组` 不能套 `分组`；`布局` 里只能放 `区域`。三栏布局写成
`布局 横排` + 三个 `区域`。

**表格数据按数据键取**，接口用 `lists` 给：

```
列表 前置 绑 prereq       显示名「前置」，数据取 prereq
```
```
设 group.prereq = {rows}
响应 lists {group}
```

一个界面可以有多张表。响应字段是白名单（`messages` `state` `stream`
`form` `lists`），写别的会被静默丢掉。

**浮层开关在地址里**：`#笔记列表?浮层=笔记&id=5`。刷新后还开着，后退键能
关，配合浮层上的 `载入` 把记录拉回来。行动作用 `打开 浮层 带 id`。

**提交时以地址为准**：地址里的参数会盖掉表单里的同名键。主键是显式字段时，
编辑框里的主键是只读的——否则改了它会改到另一条记录上（踩过）。

**控件名写错会静默变成文本框**（密码明文显示过），现在编译时会报警告，可用
的是：单行 多行 数字 日期 开关 下拉 单选 密码 选文件 选多文件。

**「提示」里不能有双引号**：原样拼进 placeholder="…"，引号把属性截断，整个
界面画不出来（jsdom 里报 InvalidCharacterError，浏览器里是白屏一块）。

几个后加的修饰：
- 界面 `侧 管理`：导航里归到右边一组（管理页），不是权限
- 界面 `端 教师` / `端 学生`：多人模式下按 /auth/me 的 role / role_label 分端——
  导航只列本端的、登录后落在本端第一个界面、直接打别端地址退回本端首页并提示；
  单人模式不分端。不叫「角色」：界面的「角色」是表单 / 列表 / 自定义
- 动作 `每隔 2`：界面开着、「当」成立时每 2 秒悄悄提交（轮询后台任务），配「隐藏」
- 列表行上的 `远程 带 id`：点了把这一行的 id 交给接口（行上的通过、重试），「当」
  里能用 `row`
- 界面上的按钮「打开」浮层时地址参数留着（`?job=3&浮层=确认`），关掉回到 `?job=3`；
  列表行上的「打开 浮层 带 id」也留着，行的参数盖在上面（`#学情?student=s1&浮层=…&note_id=5`，
  关掉回到 `?student=s1`）。行上「编辑」是把整行拷进表单、参数对得上就不调「载入」——
  行里要带全浮层要的字段（不显示的列照样能放进行数据）
- 行上的「打开」「切到」按钮也认「当」（`当 row.mine==1`）
- 接口 `返回 {"go":"#界面?k=v"}`：带参数跳过去
- **表单的初值不看实体的「默认」**：「打开 浮层 重置」之后数字框是 0、下拉是空。地址里
  没参数时浮层的「载入」不会调（「AI老师设定」页上的「新增传达」就是），默认值要接口自己
  补（`{x 或 默认}`，数字的 0 当「没填」），标签里写明「不选是…」

## 六、生成器

```
py -m gen init 项目/          建目录
py -m gen auth 项目/          用户表、登录注册，打开认证
py -m gen gen 项目/ --模板 full|private|default [--实体 x] [--覆盖]
py -m gen build 项目/         编译界面到 web/
py -m gen run 项目/           建库 + 编译 + 起服务
```

**不要对有特殊约束的表跑生成**：知识图谱的 `prereq` 表必须走带环检查的插入，
生成的普通 `INSERT` 会绕过环检查。用 `--实体` 限定。

**迁移只有「只加」一种。** 重新生成建表语句会先 `DROP TABLE`，别对有数据
的库跑。路由顶层写一行 `迁移 只加` 的项目（kg 开着），`gen run` / `ensure_db`
/ dsl_http 启动时按实体补缺的表、列、索引（`tools/migrate.py` 的
`migrate_additive`），不 DROP、不改已有列，对不上的只告警。没写这行的项目，
实体加字段要手写 `ALTER TABLE`。多列唯一写在实体里：`唯一 learner point`。

**`private` 模板**要求实体有 `owner` 列，服务器填，前端伪造无效。

**登录可开关**：路由顶层写 `认证 可选`，平时跟没写一样；启动加 `--登录`
（`gen run 项目/ --登录`、`py -m kg --登录` / `KG_LOGIN=1`）才要求登录。配套
`认证 核对 app.db user_auth`（每请求查停用、拿角色）、`认证 身份 learner 默认 me`
（引擎注入 learner：多人模式是登录的人，请求体伪造无效；单人模式照旧）、接口行
`角色 teacher`（多人模式下别人 403）；`只许 教师` / `只许 学生` 同一回事、写中文名，
按 `认证 角色 student 学生 拒绝 <说明>` 对回代号，「拒绝」后面是 403 的说明。见
tools/dsl_http.py「认证」一节。kg 的教师只能命令行建：`py -m kg 建教师 <用户名>`；
学生由教师在「学生管理」页建。kg 多人模式下教师是单独的一端：会读写学习记录的
接口都「只许 学生」（教师 403），教师只看学情、学生管理、教材导入。
**参数别叫 learner**：多人模式下请求体里的 learner 被引擎盖成登录的人，教师端
查某个学生要用别的名字（学情用 `student`）。

## 七、命名规矩

关键字、动词名、动词参数名、界面名用中文；**文件名、表名、列名、实体名、字段名、
JSON 的键用英文**。中文显示名统一叫 `label`（`name` 是标识符）。

**脚本里的变量名、脚本参数（`执行 x.zs key=值`）、SQL 参数（`:limit`）也用英文
snake_case**；路由器注入的是 `{request}` `{current_user}` `{session}` `{run_mode}`。
传给中文动词的参数字典，键照旧是中文动词参数名（`设 split_args.题干 = …`）。
`tests/dsl/test_naming.py` 扫 .zs / .sql / gen 模板，出现中文变量名就失败。

违反过多次：`entities/用户.entity`、`templates/完整/`、`kg.json` 里的中文键，
都是后来返工改的。

## 八、静默失败清单

这些都真实发生过，共同点是**不报错、结果却是错的**：

- 事务状态放在动词包模块里 → 并发时串线，请求报 500 但数据已写入
- `rowcount` 对以 `WITH` 开头的语句返回 -1 → 「影响 0 行」判断永远不成立
- 查询出错返回一行假数据 → 页面上多一行空白
- 空串不等于 NULL → 可选的外键字段留空时报「关联的记录不存在」
- 布尔值在前端：库里的 `1` 和 `true` 不相等，勾选框显示成没勾
- Jinja 注释写成 `{#- … #}` → 吃掉前面的换行，把上一行的「结束」粘过来，
  路由器静默跳过那个接口
- 探测端口没设 `SO_REUSEADDR` → 停掉服务马上重启，误报端口被占用
- 保留字写在 `设 x = ` 右边 → 当成文本，不报错
- `如果 {结构} 为空` → 平的对象展开成 `{…}`，被当成「没展开的变量」，恒为空。
  判空结构用 text 包的 `相等 {x} {}`
- 动词参数里写 `{x 或}` / `{x 或 默认}` → 参数按空格切在展开之前，被切成两个
  参数。先 `设 v = {x 或}` 再 `{v}` 传
- （已修）条件早先先展开再按空格拆，值里有「包含」「为空」、两边有空值都会切错。
  现在结构在原文上认、两边分别展开，`如果 {a} 等于 {b}` 放心写。反过来，**字面值**
  里不能有 且 / 或 / 非 / 括号（它们是结构）：`如果 {x} 等于 (A)` 报错，先
  `设 want = (A)` 再 `等于 {want}`
- 正则里的花括号：`\d{4}` `{2,3}` 原样能用（没定义的 {…} 不展开）；花括号里恰好是
  已定义的变量名就会被换掉——要找字面的「{name}」写 `{{name}}`

**判断一件事有没有做成，看的是测试和数据库里的实际内容，不是接口返回了
200。**
