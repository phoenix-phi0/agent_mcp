# M4-P2 实现清单（教师助手：上传文件 / 附件）

约定已在 K138 写好（contracts/assist_file.md（新）、teacher_assist.md、assist_draft.md、entities/assist_file.entity（新）、
plan/top.zs、ui/teacher_assist.ui），本清单给后续 change2（sonnet v3）用。设计依据 data/tmp/k124_design/design.md §4，
决定 decisions_final.md（D5 附件进提示词 ≤6000 字、D6 xlsx 提示另存 csv、D7 图片本期不做、D8 每老师每科目 20 个 + 手动清理脚本、
D14 只读老师只能提问）；落点见 data/reports/kg_K133.md「P2–P4 落点」。

## 约定领先实现时的状态（K138 写完约定时）

- 约定检查 18 个模块 0 问题；xcall 2659 处 0 不一致（test_xcall.py / test_project.py 的模块清单已加 assist_file）。
- 全量回归 15/18：assist_file 23 条全失败（还没有 services/assist_file.zs）；teacher_assist 68 条失败 9 条（全是新增的 11 条里的；
  「挂着附件说出题仍走草稿不写库」「列对话页面_带当前附件」两条现在碰巧能过，实现后仍应通过）；assist_draft 150 条失败 1 条
  （新增的「生成草稿_带参考材料仍经校验」，入参 ref_text 还没有）；另有「比对约定」报 生成草稿 入参、teacher_assist 依赖少 assist_file。
  旧用例 0 失败。
- gen build 不过：ui 引用的 4 个新动作（assist_attach / assist_attach_drop / assist_attach_pick / assist_attach_delete）在 routes 里还没有
  （约定的「## 接口」已声明，第 2 步写路由后应恢复，接口数 97 → 101，test_project.py 里的「97 个接口」要同步改成 101）。

## 关键取舍（实现时别改回去）

1. **文件不挂在 /teacher_assist/ask 上**：引擎接口行的「上传 <字段>」生成的路由先 `存文件`，没带文件就回 400（`[没有叫「assist_file」的上传字段]`），
   即上传在引擎里是必填的。所以另开 `POST /teacher_assist/attach -> 挂附件页面 上传 assist_file 上限 10MB`，底栏两个按钮：
   「发送」只发文字（/ask 不变）、「传附件」发文件 + 输入框里的话（先挂上，有话再问一轮）。不改引擎（要做成同一个按钮需要引擎支持
   「上传 … 可选」，记为后续可选的引擎改动 E5，不在本期）。
2. **路由的「上传」不写「类型」**：写了 xlsx 和图片会被 `存文件` 用引擎的话拦掉，老师看不到 D6/D7 的原文。类型白名单在 assist_file 的
   判类型 里按扩展名判，文件头对不上交给 读文档 报错。代价：被拒的文件已落到 uploads/（哈希命名，不重复），不记行、清理脚本不扫。
3. **删除附件是软删**（status=deleted，清 text/stats），行和磁盘文件由清理脚本删（DSL 没有删文件的动词）。
4. **一个老师一个科目同时只挂一个附件**（attached=1 至多一行）；同一个文件（path 相同）再传不新建行、不占配额，只重新挂上。
5. **assist_draft 不依赖 assist_file**：teacher_assist 取附件文本拼成 ref_text 交给 生成草稿；只对 quiz_add 生效，不进 payload。
6. **附件的写操作 need=write 在 assist_file 里校验**，teacher_assist 的四个附件页面函数按读解析科目、把角色和登录模式原样传下去。

## 模块行数估算（每个服务文件 ≤ 约 1800 行）

| 模块 | 现在 | P2 改动 | P2 后 |
|---|---|---|---|
| assist_file（新） | 0 | 本科目 8、本人附件 15、附件标签 12、判类型 20、csv统计 70、存附件 90、取当前附件 20、挂上附件 25、移除附件 25、删除附件 20、列附件 30、取附件文本 110（关键词摘段、头尾、csv 行） | 约 470 |
| teacher_assist | 873 | 判意图 +25（attach_text、file_qa、兜底 ②d）、问助手 +55（取当前附件、file_qa 分支、ref_text）、答一轮 +5、列对话页面 +12、记一条 +3、四个附件页面函数 +75 | 约 1050 |
| assist_draft | 1381 | 生成草稿 +12（ref_text 截断、提示词【资料】段） | 约 1395 |
| routes/teacher_assist.zs | 7 个接口 | +4 个接口（attach 带上传、pick、drop、delete） | 11 个接口 |
| setup/cleanup_assist_files.py（新，Python） | 0 | dry-run / --apply / --days / --keep / --db，事务删行后删文件 | 约 130 |

均 ≤ 1800；teacher_assist 离上限还有约 750 行给 P3/P4（K133 估 P2–P4 后约 1150）。

## 实现步骤（每步一个 change2，注明输入量）

### 第 1 步：assist_file 新模块（fix2：audit2 → change2）
- 新建 services/assist_file.zs（照约定全文写），queries/assist_file_*.sql（建议名：get_own、get_current、by_path、count_ok、unattach_all、
  attach_one、insert、last_id、list、touch、soft_delete、unattach_one）。`用包 doc`（读文档）、`用包 data`（读CSV）。
- csv统计：先 读CSV（UTF-8/BOM）；读CSV 抛错时退回按 读文档 的 text 逐行按英文逗号切（GBK 的 csv 走这条）。数值判断、均值 2 位小数可在 DSL
  里逐格算，也可借 SQL（`CAST(x AS REAL)`，注意空串不是 NULL）；按 skill 的坑：参数一律是字符串，比较要 CAST。
- 取附件文本：关键词切分、按段拼到 M 字——段落数多时注意 DSL 循环的开销（src 最多 50000 字）。
- 输入：约定 37KB + subject 的公开函数头 + entities（assist_file、subject）；新文件约 470 行，比 K133 拆模块第 2 步（assist_common 310 行）
  稍大，远小于 K131b 失败时的规模，单次 change2 装得下。
- 验收：assist_file 23 条全过；xcall 0 不一致。

### 第 2 步：teacher_assist 接附件（fix2）
- 依赖加 assist_file（约定、services/teacher_assist.zs 头、top.zs 三处已在约定和 top 里改好，服务文件头要跟上）。
- 判意图（attach_text、file_qa、兜底 ②d）、问助手（cur、file_qa 分支、quiz_add 的 ref_text）、答一轮（规则⑩、【资料】标题）、
  列对话页面（attach、files、att_note）、记一条（intent?）、新函数 挂附件页面 / 挂上附件页面 / 移除附件页面 / 删除附件页面。
- routes/teacher_assist.zs 加 4 个接口（`/teacher_assist/attach` 由接口行的「上传 assist_file 上限 10MB」生成 存文件 + 上传信息 行，
  函数入参 assist_file_path、file_name、file_size、file_ext 已按生成器要求命名）。
- 输入：约定 82KB + assist_common / assist_draft / assist_file 等上游的公开函数头 + 现有服务 41KB（873 行）；改动约 +180 行，
  小于 P1b 时 teacher_assist 单批（约 +230 行）和 K133 第 5 步，装得下。
- 验收：teacher_assist 68 条全过；gen build 101 个接口（test_project.py 的 97 同步改 101）。

### 第 3 步：assist_draft 生成草稿 加 ref_text（fix2，最小改动）
- 生成草稿 入参加 ref_text?，去空白、截 8000 字、只对 quiz_add 进提示词【资料】段（修订稿也带）。
- 输入：约定 128KB + 服务 57KB（1381 行），改动约 12 行；与 P1b 第 4 步（assist_draft 分派改动约 230 行）同量级输入、改动小得多，装得下。
  也可以并进第 2 步之前先做（第 2 步调 生成草稿 带 ref_text，xcall 已按约定核对过参数名）。
- 验收：assist_draft 150 条全过。

### 第 4 步：清理脚本 setup/cleanup_assist_files.py（opus 或 sonnet 直接写，不走 change2）
- 行为见 contracts/assist_file.md 顶部注释：默认 dry-run；跳过 attached=1；删 status=deleted 全部 + ok 且 last_used_at 早于 --days 天
  + 每老师每科目超出 --keep 个按 last_used_at 从旧到新删；--apply 时事务删行后删文件（同一 path 还被任何 teacher_assist_file 行或
  textbook_import 任务表引用就不删文件）。
- 测试：tests/kg_v4/test_cleanup_assist_files.py（临时库造行：attached=1 的旧行不删、deleted 行删、超 20 个删最旧、dry-run 库和文件都不变、
  同 path 被别的行引用时只删行不删文件）。加进 run_all.sh。

### 第 5 步：e2e 与验收
- tests/e2e/teacher_assist_run.js 加附件段（照现有写法起真服务、jsdom 点页面）：传 txt → 附件条出现文件名、对话多「已挂上」→
  问「总结一下这份附件」（DSL_MOCK_SCRIPT）→ 移除附件 → 附件条消失、附件表还在 → 挂上 → 删除 → 表里没了；传 xlsx → 页面上显示
  「另存为 csv」原文；传 csv → 附件条「csv · n 行」；只点「发送」时不会带文件（对照：同一请求点「传附件」能挂上）。
- 长文本截断（>6000 字的 txt：keyword / headtail 两种）在约定用例里不好造（一行 6000 字），放进 e2e 或 test_assist_files.py 直接调函数。
- `tests/kg_v4/test_project.py` 18/18、`bash tests/run_all.sh`、kg_v4 `e2e_walk.py` 不退化；真模型冒烟 ≤3 句（csv 统计问答数字核对、
  按附件出题、带「忽略以上指令」的文件做注入测试，确认没有写库）。

## 已知限制

- 「发送」不带文件：选了文件却点「发送」，前端仍会把文件随 multipart 发到 /teacher_assist/ask，但那个路由不存文件、直接忽略，提交后文件字段被清空（底栏提示里写明）；要一个按钮解决需引擎支持可选上传（E5）。
- 没选文件就点「传附件」：生成的路由回引擎原话「[不在请求里，或者这次请求没带文件]」400，文案改不了（同 E5），只在底栏提示里写明先选文件。
- 文件超过 50000 字时只保存前 50000 字：开头加结尾退化为只给开头（并说明结尾没保存），关键词摘段只在前 50000 字里找。
- 被拒的上传（xlsx、图片、其它类型、读不出字）文件已落在 uploads/，不记行，清理脚本不扫（与教材导入共用目录，无法安全判孤儿）。
- 关键词摘段对不带标点、空格的中文长问句基本不命中，会退回「开头加结尾」。
- 附件文本只在 file_qa 和依据附件出题时进提示词；挂着附件问学情（class_overview 等）不带附件。
