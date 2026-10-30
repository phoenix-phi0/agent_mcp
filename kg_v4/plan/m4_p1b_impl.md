# M4-P1b 实现清单（教师助手：改 AI 老师设定 + 加知识点/条目草稿）

约定已在 K130 写好（contracts/teacher_assist.md、plan/top.zs、entities/teacher_assist.entity、ui/teacher_assist.ui），
本清单给后续 change2（sonnet v3）用。设计依据 data/tmp/k124_design/design.md §2、§3、§7「P1b」，决定 decisions_final.md
（D2 partial、D3 7 天撤销、D4 修订稿、D14 只读老师、D15 兜底判意图）。P1 的草稿框架（表、状态机、claim 抢占、确认/放弃/撤销、
页面函数、路由）已在 master，P1b 只在框架上加两种 kind，不加表、不加接口、不改路由。

kind 命名：设定用设计稿的 `setting_save`；知识点类把设计稿的 kg_point_add / kg_item_add / kg_edge_add 合成一种 `kg_add`
（payload 里 points / items / edges 三个列表），一份草稿就能「建一个知识点连同它的条目和前置边」，partial 与撤销按条目逐条记。

约定领先实现时的状态（K130 写完约定时）：约定检查、xcall 全过（2542 处 0 不一致，「提供」0 未列）；全量回归 12/13，
只有 teacher_assist 不过：220 条用例失败 46 条，全部是本次新增的 58 条里的（旧 162 条 0 失败，其中「校验草稿_类型不对」
「生成草稿_类型不对」原来拿 setting_save 当非法类型，已改成 other；新增里 12 条现在碰巧能过，实现后仍应通过）；「比对约定」报缺 9 个新私有函数。gen build 97 个接口照常通过（ui 只多一个「显示」，不引用新动作）。

## 只有一批：teacher_assist（58 条新用例）

K127 的经验：同一模块内暂存约定会自相矛盾（正文互相引用），所以 teacher_assist 一轮 audit2 → change2 → fix2 做完，
不拆批。teacher_rules、kg 两个模块**不用改实现**：只在 top.zs 的「提供」里补了导出（函数行为不变），xcall 已过。

### 新增私有函数（9 个）

| 函数 | 说明 |
|---|---|
| 设定候选 subject_id | teacher_rules.列设定 → 按 id 降序前 40 条 → 逐条 teacher_rules.取设定 拿 subject_id 分 editable（本科目）/ readonly（0） |
| 图谱编号前缀 learner subject_id | 日语空串；其它 subject.科目详情 取 code 拼「code.」 |
| 编号合规 code prefix | 照抄 kg 编号格式检查 的正则和前缀规则（kg 的是私有函数，不能调） |
| 校验设定草稿 payload subject_id | settings 1–10 条；禁键 scope/subject_id/setting_id/enabled/version/author；target_id → teacher_rules.取设定（404、subject_id=0 都进 errors）；edit 时缺省键取当前值；student 走 匹配学生；card 必须有 keywords |
| 校验图谱草稿 payload learner subject_id | points ≤10、items ≤30、edges ≤30；编号合规、已存在（kg.取知识点 / kg.取条目）、草稿内重复；条目的所属点/前一个条目要在草稿前面或库里；边：两端存在、不自环、已存在（kg.列前置）、成环（kg.列后代 ∪ 草稿边） |
| 执行设定草稿 draft current_user subject_id | 逐条 teacher_rules.保存设定（add 不传 setting_id；edit 先 取设定 存改前值进 snapshot，subject_id=0 的直接记失败）；不抛错 |
| 执行图谱草稿 draft current_user subject_id | 点 → 条目 → 边，kg.建知识点 / kg.建条目 / kg.加前置边；边的 created 原样记（0 = 已存在，撤销不删）；不抛错 |
| 撤销设定草稿 draft subject_id | 先全量预检（当前值 6 键 == written 且仍属本科目；edit 的被删 → 阻断；add 的被删 → gone），有阻断抛 409 一条不动；再倒序 删除设定 / 用 snapshot.before 调 保存设定 恢复 |
| 撤销图谱草稿 draft subject_id | 先查还在不在（gone），再 kg.查引用 扣掉本草稿自己的条目/边、忽略「教师助手对话」，有剩余引用抛 409 一条不动；再 边 → 条目倒序 → 点倒序 删 |

### 修改的公开函数

| 函数 | 改什么 |
|---|---|
| 判意图 | draft_kind 多 setting_save、kg_add；兜底加 ②b（设定/作者注/关键词卡/记住/AI老师 + 加/改/新建/设/写/记）②c（知识点/条目/前置 + 加/建/新增/添），放在 ② 之后 ③ 之前 |
| 问助手 | D14 模板话改文案；①b 中文类型名映射多两种；② 追问文案；③ setting_save 不自动补上轮学生 |
| 取助手上下文 / 答一轮 | chitchat 功能说明、规则⑤ 文案 |
| 类型名 | setting_save→改设定，kg_add→加知识点 |
| 校验草稿 | kind 白名单 4 种；分派到 校验设定草稿 / 校验图谱草稿 |
| 生成草稿 | kind 白名单；两种新备料（不调模型的 ask 分支：setting_save 学生 none/many）；提示词与 问JSON 格式；调 校验草稿 时补 learner=current_user |
| 取草稿 | result_text 两种新格式；新键 compare_text（设定改前改后，未确认时现取 teacher_rules.取设定） |
| 确认草稿 | 分派到 执行设定草稿 / 执行图谱草稿，按 D2 落 done/partial/failed；setting_save 同一条落库 UPDATE 写 snapshot；summary 文案 |
| 撤销草稿 | 分派到 撤销设定草稿 / 撤销图谱草稿；抛 409 时同 quiz_add（回 old_status、写 error、清 claim、原样抛）；正常返回同 relay_add 的落库规则；新报错行 3 条 |
| 撤销草稿页面 | 报错行同步（实现不变，原样抛） |

### 新查询（建议名）

- `teacher_assist_draft_finish_snap.sql`：同 teacher_assist_draft_finish.sql 再多写 `snapshot = :snapshot`，只给 setting_save 确认用
  （别动原 finish：撤销落库也走它，不能把 snapshot 清掉）。
- 其余全部经跨模块调用（teacher_rules / kg / subject），不直读别的模块的表。

### 注意

- 被调写函数一律带 subject=subject_id、不传 current_role / auth_mode（权限已由 确认草稿 / 撤销草稿 按 need=write 校验，同 P1 的 保存传达）。
  所以 own 校验不会生效——全部科目(0) 的设定必须由本模块自己挡（校验时、确认时、撤销预检时各挡一次），不能指望 teacher_rules。
- 设定比较按文本：库里 NULL、空串、整数 1 与 "1" 都要规整后再比；written 取 保存设定 的返回值（含 enabled）。
- kg.查引用 的 source 名是中文原文（下挂条目、前置边、对照、后一个条目、题目、课文挂接、单词、作答记录、掌握记录、得分记录、默写进度、教师助手对话），
  扣减规则按 source 名写。
- 用例里的模拟模型回占位值，生成草稿 的正路走不到（同 P1）：正路放到 e2e。

## 批后验证

- `tests/kg_v4/test_project.py` 全绿（回归 13/13，teacher_assist 220 条）；`tests/kg_v4/test_xcall.py` 0 不一致。
- e2e `tests/e2e/teacher_assist_run.js` 追加两段（DSL_MOCK_SCRIPT 给合法 JSON）：①「给全班加一条作者注：多鼓励」→ 确认 → AI 老师设定页能看到 →
  在设定页改一下内容 → 回助手点撤销 → 409 提示、设定不动；再生成一份 → 确认 → 撤销 → 设定消失。②「加个知识点 P2 和条目 I2，前置 P1」→
  确认 → 图谱管理页看到点、条目、边 → 撤销 → 三样都没了；再来一次但先给 I2 出一道题 → 撤销 409、原因里写「题目1」。草稿详情浮层里
  「设定改前改后」那段在改已有设定时出现、新建时不出现。
- `bash tests/run_all.sh`、kg_v4 `e2e_walk.py` 不退化。真模型冒烟 ≤3 句（设定 1、知识点 1、「把那条作者注改成…」走 target_id 1）。

## 已知限制

- 撤销「先预检、再逐条写」不是原子的：预检通过之后、写之前有人改了设定或加了引用，会被覆盖或由 kg 自己报 409（后者记进该条 error，
  草稿回到原状态，可再点撤销）。
- 跨科目编号重号（日语科目建了一个形如「math.x」的编号）在草稿阶段查不出来（kg.取知识点 只查本科目），确认时 kg.建知识点 报 409
  「编号已被其他科目使用」，记为该条失败（partial）。
- 设定撤销会让 version 再加 1（保存设定 的现有行为），「只用于下一条」的作者注撤销恢复后会重新可用。
