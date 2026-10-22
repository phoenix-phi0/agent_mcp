# DSL 速查

自己用的。写「怎么用」和「哪儿会咬人」，不写「为什么这么设计」——
那些在 Notion 的「MCP 服务器」页。

---

## 一、跑起来

```
py -m tools.dsl 脚本.zs            命令行
py -m tools.dsl 脚本.zs 键=值 …    传参数（见下）
dsl_run(script=...)                MCP 工具，默认假客户端不花钱
dsl_run(script=..., real=True)     走真模型
cd dsl && py run.py scripts/x.zs   干净环境，数据隔离在 dsl/work/
```

### 顶层脚本传参

`python -m tools.dsl 脚本.zs 键=值 键2=值2 …`：注入成脚本变量。脚本头有
`# 参数：` 声明（写法同下面「动词的参数」）时按同一套规则绑定——必填缺了报错、
`名?` 不传为空串、`名=值` 不传用默认值、给了声明里没有的键报错、同一键给两次
报错；没有声明就把给的键原样注入，不校验。`--trace` 放哪个位置都行。

Python 接口 `DSLEngine.run(script, params={...})`、`run_file(path, params={...})`、
模块级 `run_script(path, params={...})` 走同一绑定函数（`tools.verbs.bind_top_params`）。

---

## 二、语句

### 配置

```
用包 common quiz db          声明动词包，同时开严格模式
模型 glm-4.6
系统 你是日语教师
系统 你是教师 附 prompts/teacher.md
温度 0.5
```

「用包」之后打错的动词名会报错而不是当文本。

### 变量

```
设 名字 = 世界
设 问候 = 你好，{名字}
设 会话.题号 = q1              点号路径，中间层不存在会自动建
设 深.一.二 = 值
```

`{名.路径}` 取值，数字段当下标，负数从末尾数：`{题目.-1.id}`。
取不到时**原样保留**成 `{名.路径}` 字面量——为了拼写错时看得见。

读写对称：能读 `{会话.题号}` 就能写 `设 会话.题号 = x`。

### 调模型

```
问 答案 = 解释这个词
问JSON 决策 = 提取意图：{输入}　按这个格式：{"意图":"","课程":""}
流式 讲解 = 讲一讲                边生成边打印
对话 回复 = 今天学什么            多轮，进历史
判定 结果 = 这句对吗 正确→○ 错误→✗ 否则→?
```

三个后缀，剥离顺序是**重试最外、然后带工具、最后挂载**：

```
问 摘要 = 概括一下 附 a.md,b.md
对话 回复 = {输入} 带工具 挑题,题目数 最多 3 轮
问 答案 = 出一道题 重试 3 次 直到 包含 答案
```

### 历史

```
重置
读历史 sessions/{学习者}.json
存历史 sessions/{学习者}.json
修剪历史 20                    只留最近 20 条
修剪历史 8000字                只留最近 8000 字
修剪历史 20 8000字             两个上限都满足
```

**引擎不自动裁剪**，「对话」每次把全部历史发出去。挂了文件的那条尤其
大，之后每轮重发。

### 文件

```
打印 {内容}
保存 out.md 正文\n第二行
追加 log.txt 一行
读取 文本 = a.md
读JSON 配置 = config.json
读JSONL 题库 = content/n2n3/题库/doushi_01.jsonl
```

路径都限制在 workdir 内。

### 流程

```
如果 {结果} 开头是 ○
  打印 对了
否则
  打印 错了
结束

遍历 词 于 犬，猫，鸟
  打印 {词}
结束

遍历 题 于 {题库}              列表变量直接遍历，每项可以是对象
  打印 {题.id}
结束

逐项 词 于 犬，猫               自动加标题，块内没打印就输出最后一次生成
  问 讲解 = 解释「{词}」
结束

执行 子脚本.zs 课程={课程} 数量=5   # 先找本脚本文件同级目录，再找工作目录；同名同级优先
返回 {"code":0}                立即结束，后面的行不跑
返回 {"error":"没找到"} 404
```

`执行 x.zs` 找脚本的顺序：① 正在跑的这个脚本**文件**所在目录（同级）下的 `x.zs`；② 工作目录（项目目录）下的。
两处都有同名时同级优先。同级查找只认该目录内的文件（`..` 跳出去的不算，照旧按 ② 报越界）；字符串脚本
（不是从文件跑的）没有同级目录，只走 ②；子脚本里再 `执行`，同级 = 子脚本自己的目录。`后台执行`、`并行执行`、脚本动词的查找不变。

### 事务

```
用包 db

事务 学习.db
  写库 学习.db 记作答 学习者={who} 题号={q}
  写库 学习.db 加错题 学习者={who} 题号={q}
结束
```

块正常结束就提交，块内任何一步出错就回滚再抛。「返回」在事务里算成功
并提交。不支持嵌套。

### 业务层（services/<模块>.zs）

一个文件一个模块、多个具名函数，放在项目目录下 services/（和 routes/ queries/ scripts/ 并列）。
比「一个 scripts 文件 = 一个函数」多了：入参声明、公开/私有、模块依赖、业务错误、跨函数共用事务。

```
业务 progress                        # 模块名 = 文件名（services/progress.zs）
  依赖 graph                         # 可调用哪些别的模块；不写就不能调
  用包 db                            # 本文件里函数共用的包

  公开 函数 记作答 learner point_code question_no correct answer? pass_line?
    设 p = 调用 graph.取知识点 code={point_code}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    事务 app.db
      设 r = 调用 重算得分 learner={learner} point_id={p.id} pass_line={pass_line}
    结束
    返回 {"score": {r.score}}
  结束

  函数 重算得分 learner point_id pass_line?    # 不写「公开」= 只给本模块的函数用
    ...
  结束
结束
```

- 入参写在函数头，`?` 结尾是可选（不传是空串）。函数是独立作用域：里面只有入参，看不到接口的
  `{request}`、`{current_user}`、`{learner}` 等，要用就当入参传进来。
- `返回 值` 结束函数交出结果（值是 JSON 就是结构）；没有 `返回` 得到空串。
- `报错 <4xx码> <文字>`：业务错误，沿调用链往上传，到接口层自动变成 HTTP `{"error": 文字}` + 该码
  （接口里、scripts 里也能写）。第一个词不是 400–499 的码时仍是 common 包的「报错」动词（500）。
- 调用：`设 r = 调用 模块.函数 键=值 …`（接口、业务函数、scripts 里都能用，「执行」同义）；同模块里
  可以只写 `调用 函数名`。`执行 x.zs` 照旧是跑脚本。
- 接住业务错误：`设 r = 调用 模块.函数 … 出错时 e`，出错后 `{e.code}` `{e.error}`，r 是空串；
  没出错 `{e}` 是空串（用 `如果 {e} 不为空` 判断）。没写「出错时」就一路传上去。
- 规则（运行时和加载检查同一套）：只能调「公开」函数（同模块的业务函数除外，接口不算）；
  跨模块必须在调用方模块的 `依赖` 里；接口文件属于哪个模块按文件名 `routes/<模块>*.zs`
  （模块名是文件名前缀，取最长的），对不上任何模块的接口 / 脚本只能调公开函数、不查依赖；
  必填参数必须给、不认识的键报错；调用深度上限 32（环境变量 DSL_SERVICE_MAX_DEPTH）。
- 事务：外层 `事务` 里调用的函数，里面的写库都在同一个事务（库连接挂在线程上，函数在同一个线程跑）；
  函数里自己写的 `事务` 在外层事务里并入外层（不另开、不提交），单独调用时自己开自己提交。
  接住（出错时）的错误不回滚外层事务已做的写入——要整体回滚就别接，或接住后再 `报错`。
- 加载：Router / 引擎解析一次缓存，文件改了下个请求重载；解析错误、依赖不存在、依赖成环在启动时
  拒绝加载。加载检查（loadcheck）还查：调用不存在 / 非公开的函数、跨模块未声明依赖、缺必填 / 多
  出未知键、`报错` 的码不是 4xx。参数核对把函数入参当作函数体里已定义的变量。

---

## 三、条件

```
包含 不包含 等于 不等于 为空 不为空
大于 小于 不小于 不大于 开头是 结尾是
```

两侧都能转数字时按数值比较。

**符号写法**：`>` `<` `>=` `<=` `==` `!=` 是 大于 小于 不小于 不大于 等于 不等于 的别名，
全角 `＞ ＜ ≥ ≤ ＝＝ ≠` 也认，语义完全一样；文档和生成的代码以中文为规范写法。
结构在展开前的原文上认，所以 `{变量}` 的值里有 `>`、`==` 不影响；`{…}` 外的字面值里
含这些符号时跟中文运算符一样会被当成运算符（要比的值带符号，先「设」进变量）。
单个 `=` 不是运算符，报错「比较用 等于 或 ==」。

**「为空」认四种**：空串、空列表 `[]`、空对象 `{}`、以及**没展开的
`{变量}`**。最后一条是关键——未定义变量原样保留成字面量，那在语义上
就是「没有值」。

---

## 四、会咬人的地方

### 动词参数不能有空格

**全角空格也不行**——`normalize` 会把它转成半角，于是多切出一个参数。
全角空格在编辑器里看不出来，这个坑比半角的隐蔽。

要传带空格的内容：

```
设 进度文本 = {课程}　{对}/{总}
状态 stat {进度文本}
```

### SQL 的参数一律是字符串，数值比较要 CAST

```sql
HAVING count(x) >= :下限                    -- 恒假，而且不报错
HAVING count(x) >= CAST(:下限 AS INTEGER)   -- 对
LIMIT CAST(:条数 AS INTEGER)                -- LIMIT 同理
```

SQLite 有列亲和性，所以 `WHERE views > :下限` 能工作。但左边一变成
表达式（`count(*)`、`sum(x)`）亲和性就没了，比较退回纯值比较，而
**文本永远大于数字**。

### 「判定」的分支不发给模型

分支列表只在本地匹配模型回复的开头。期望的选项要自己写进提示词里，
否则模型回一段话，`startswith` 不命中，直接落到「否则」。

### 别的

- 「判定」的分支输出不能含空格
- 全角逗号只在列表位置当分隔符，正文里原样保留
- 关键字后紧跟汉字时不算关键字：「打印机 状态」不会被当成「打印」
- `查一值` 只适合单列查询，多列会拿到第一个字段
- 动词返回列表时保留结构，能直接 `遍历`；返回给人看的东西该返回文本

### 命名约定（数据/标识层英文，语法层中文）

语法层（关键字、内置动词名、动词参数名、约定格式关键字）保持中文；
数据和标识层（动词返回字段名、状态/枚举值、模型回复 JSON 键、业务函数名）
一律英文 snake_case；显示文字（打印、报错文案、docstring 里给人看的话）
保持中文。

**不在改名范围内（R6 收尾时再次确认，以后也不要去改）**：
- **状态/枚举值**：`成功`/`失败`/`超出预期`、`通过`/`跳过`、`是`/`否` 等照旧，
  只有装它们的**字段名**改英文（如 `{status: "成功"}`）。
- **布尔的表示方式**：返回 `"是"`/`"否"` 字符串的动词不改成 Python 的
  `True`/`False`。C1（commit 327e821）曾经把其中 5 个动词改成真布尔，
  R5 已经逐行退回原样（见下）；以后也不要再改这一类。
- **业务函数名**：`services/*.zs` 里 `公开 函数 记作答 ...` 这类名字不改。
- **语法层**：关键字、内置动词名、动词参数名、约定格式关键字不改。

### 入参名约定（D4）
- **动词的入参名用中文**（`需求=` `模型=` `问题=` 等，不改）。
- **顶层脚本（`核查.zs`、`修改.zs`、v3 入口）的入参名用英文**：核查 `req task? llm=sonnet`，
  修改 `req issues=latest task? llm=sonnet retries=3`（`model` 是引擎关键字别名不能当变量名，所以用 `llm`）；
  `读问题清单` 的 `问题` 同时认 `latest` 和 `最新`。取值（是/否、最新、成功…）仍是中文。
  宿主（`core.run_entry` 的变量键、`__main__.py` 的 `extra_vars`）按这些英文名注入。
- **新写的业务函数入参用英文**。

### 核查.zs（程序检查用动词，判断处派子任务）
旧的 `核查` 动词（程序检查 + 模型调用合在一起，按 hash 缓存）已删除，不留兼容壳。`核查.zs` 现在是：

```
设 a = 全局检查                   # {count, by_module, summary, items}
设 b = 全量回归                   # 有代码才跑；只检查，不重做、不改 state；多返回 failed:[{module,reason}]、failed_text
设 c = 接口冒烟                   # 同上；完整结果存 out/smoke_<n>.json/.txt；多返回 failed、failed_text、notes、notes_text
                                  # （旧参数 方式=核查 仍接受，等同默认；其他值报错）
设 files = 列表加项 …             # plan/catalog.md、plan/top.zs、contracts/<模块>.md（有 top 才加）、需求全文
设 p = 派任务 {desc} {files} {logic} found:是否,items:列表   # 规划层一个子任务（不读代码）
设 s = 存问题清单 程序={a} 回归={b} 冒烟={c} 规划={p}
```

- 程序检查类动词统一返回 `{count, items:[{issue, modules, basis}], summary}`，modules 是逗号隔开的模块名。
  `全局检查` 的 count / by_module / summary 保持原样（只含方法+路径 / 表重复），items 同 `issues.program_items`（含依赖与顶层不一致）。
- `派任务` 的入参是文件名列表：工作目录（项目目录）内的文件由它读出，每个文件最多 400 行；需求全文直接当一项文本放进去。
- `存问题清单` 的参数都可省：`程序 回归 冒烟 规划`。规划 接 `派任务` 的返回：
  status 非成功的记入返回的 `unchecked`（`{module, reason}`，**不能当作没问题**）；`found` 与 `items` 前后矛盾、
  缺 issue/modules/basis 的条目丢弃并记入 `dropped`（带原文，不重调模型）。
  合并 → 按（issue, modules）去重 → 统一序号 → 存 `plan/issues/<序号>.md`；返回 `{path, count, unchecked, dropped}`。
- 命令行：`python -m tools.dslagent v3 audit --req … --project … --out … [--task …]`。
- 没有 plan/top.zs 时也能跑：全局检查 0 条，回归 / 冒烟跳过，规划层照派。

### 最终对照表（字段名，R1/R3/R4 的改动汇总，权威版本）

「全仓一张对照表」（R1–R4 各条按它改，新字段按同风格补上）：

| 旧（中文） | 新（英文） | 旧（中文） | 新（英文） |
|---|---|---|---|
| 状态/原因/停在/返回 | status/reason/at/returned | 结果/思路 | result/thought |
| 脚本/参数 | script/params | 花费/调用/轮/模型/记录目录/秒 | cost/calls/round/model/log_dir/secs |
| 轮数 | rounds | 一致/差异 | consistent/diffs |
| 全过/失败/总数 | all_passed/failures/total | 问题/摘要/条数/状态 | problems/summary/count/status |
| 去掉/加上 | removed/added | 新建/已有 | created/existing |
| 路径/内容 | path/content | 按模块 | by_module |
| 检查数 | checked | 实体数 | entity_count |
| 模板 | template | 功能 | features |
| 调用上限 | call_limit | 角色 | roles |
| 角色模板 | role_template | 解析 | parsed |
| 未实现/未实现列表 | unimplemented/unimplemented_list | | |
| 改了/没变 | changed/unchanged | 删了/写了 | removed/written |
| 新建/已有/新建数 | created/existing/created_count | 次数（规划一份的重试计数） | attempts |
| 问题/涉及模块/依据（模型回复） | issue/modules/basis | 通过/问题列表（模型回复） | passed/issues |
| 标签（模型回复） | label | 理由（模型回复） | reason |
| 条目序号/判定/依据（模型回复） | item/verdict/basis | | |

没碰、按规则排除的：`功能`/`角色` 等顶层键下面**嵌套**的字段（如每个功能项
的 `名`/`sql`/`接口`/`规则`/`界面`、接口项的 `角色`/`路径`/`动作`）——那是
`packs/newproj` 的模型 JSON 回复 schema，还没做（见下「还没覆盖」）；
`tools/dslagent` 内部 `c.log(...)` 记的账本/日志字段（如 `全局检查.py`、
`检查规划.py` 里 `条数=`/`问题=` 这类关键字参数名）不算「返回给脚本/模型的
结构」，原样留着。

### 回复格式键（终止 / 派任务 / 并行执行）

- `engine.halted`、`设 r = 执行 子.zs` 的结果键：`{status, reason, at}`
  （`status` 的值仍是中文 成功/失败/超出预期；`终止 {r.status}` 认英文也认中文）。
- `派任务` / `并行派任务` / 补改 / 工具模式子任务 的结果键：
  `{result, status, reason[, thought]}`；解析模型回复兼容旧中文键
  （`tools/json_repair.py` 的 `normalize_keys`），产出英文键。
- `并行执行` 每项结果键：`{script, params, status, reason, at, returned}`；
  输入端 `脚本`/`script`、`参数`/`params` 两种写法都认（原来就是双语，不是
  本次新加的兼容）。

### kg 别名 / 为 kg 保留的中文清单

`kg/` 代码本身一行没改。核实下来（R1–R5 全部完成后），**到目前为止没有任何
一个 kg 实际在用的字段被改名**，所以没有、也不需要 `test_naming.py` 里原计划
的 `ALIAS_KEYS` 双键白名单机制——不是「忘了做」，是改的范围和 kg 用到的范围
正好没交叉。专门为 kg 保留、以后也不要改的中文键：
- `verbs/quiz/_verbs.py` 的 `判对错`/`拆选项` **入参**结构：
  `题型`/`答案`/`可接受`/`作答`、`题干`/`选项`/`选了`/`种子`——
  `kg/routes/quiz.zs`、`kg/scripts/quiz_pick.zs` 直接拿这些中文键构造调用，
  kg 自己的 SQL 列名也是这几个词（这两个动词的**返回值**已经是英文键
  `{correct, mine}`/`{stem, options, picked, answer_key}`，入参和返回不是
  一回事，只有入参留中文）。
- 题库 jsonl 外部数据文件字段（`课程`/`考点`/`难度`/`题型`/`题干`/`答案`/
  `解析`）：读入照旧，不迁移数据文件，也不是「动词返回键」。

### 还没覆盖的范围（真实剩余项，R2 已核实纠正过一次）

- R2 曾经列的 `verbs/db`/`common`/`http`/`quiz` 四处「没做完」，逐文件通读
  后证明是**误判**（基于早期粗略 grep 的印象）：`db` 的「错误」现在直接
  `raise` 不返回字典；`common`「日期」「时间戳」是参数取值不是返回键；
  `http`「上传信息」已经是英文键，「哈希/时间/原名」是 `存文件` 的 `命名`
  参数取值；`quiz` 全部动词返回纯文本或已是英文键。这四处**不需要再改**，
  已从「待办」里去掉。
- `packs/newproj/prompts/` 下十余份模型 JSON 提示词（`sys_plan.md`、
  `sys_llayer.md`、`sys_mplan_{ent,flow,iface,sql,ui}.md` 等）和消费它们的
  `verbs/newproj/defs/` 校验动词：字段名还是中文，没有动——牵动整条生成
  管线的内部协议，量级比本次已做的大，留给专门的后续任务。
- `agents/bound_table_fill.md` + `verify/bound_table.py`/`verify/asserts.py`
  的「期望表」协议（字段「规则/函数/参数/断言/期望/期望包含/…」）：没有动，
  同上留给后续任务。
- `verify/code.py`/`fix.md`/`bfix.md` 里嵌套在 `结果`/`result` 内的 `说明`
  字段：R1 定性为「补改自己的记账字段」，不算数据层返回键，故意不改。

**C2（dslagent，范围已查清，预算打不住，没动代码）**：核实下来
`tools/dslagent/verbs/` 下用 `"是"/"否"` 字符串当返回字段的有 **29 个
Python 动词文件**（`verbs/code/defs/`：写文件、删文件、推理、撤回、改文件、
改模块名、核对范围、跑测试、运行代码；`verbs/dslproj/defs/`：加载检查、
比对约定、跑用例；`verbs/newproj/defs/`：`_gen`、`_gencore`、参数核对、
拆分隔块、校验分层清单、校验实体、校验清单、校验角色、核对规则、检查项目、
生成增删改查、读原文、项目摘要、预编译sql；`verbs/v3/defs/`：复核约定、
已完成、标记完成、检查规划、记验收），且不少字段被 `tools/dslagent` 里的
Python 代码直接用 `=="是"` 字符串比较消费（例如 `verify/code.py`、`v2.py`、
`legacy/reason_rules.py` 对 `passed` 字段），和 C1 遇到的情况一样，要跟着
全量核对调用点、改了不能只过 `.zs` 脚本的 `等于 是/否` 还要改这些 Python
侧比较，量级比 C1 更大，这条任务的预算（$8）更打不住，没有动这部分代码。
另外发现 spec 要求「C1 加 `tests/dsl/test_naming.py` 检查 `返回 {...}`/
Python 动词返回字典字面量的键必须英文」这一步 C1 本身也没做（见上面
C1 的「没做完的」第 5 条）——`tests/dsl/test_naming.py` 现在只查变量名/
脚本参数/SQL 参数（含 `tools/dslagent/verbs` 下的 `.zs`），不查返回键，
所以 C2 要求的「把这个检查扩展到 `tools/dslagent/verbs`」缺前提，要等
C1 那条先补上这个检查器（哪怕先只对 `verbs/` 生效）才能扩展，否则现在
扩了会在 29 个文件上整批报错。`DSLAGENT_FUNC_NAMES=any` 开关与约定检查
对业务函数名要求英文（新写报错、盘上已有只警告）同理没做：约定检查目前
按纯文本解析约定，不知道某个函数名是不是「新写的」（没有「该函数是否已有
对应 services 文件」这个上下文传进来），要先理清这条信息流才能分新写/
已有两档，风险和工作量都不小，这次没碰。`记作答`（`verbs/dslproj/`、
`v3/prompts/contract.md`、`packs/README.md` 等处的业务函数名示例）同时是
`tests/dsl/fixtures/service_layer/`、`tests/tools/fixtures/dslproj_solution/`、
`tests/tools/fixtures/v3_solution/` 等多处测试夹具里真实用到的函数名，不是
单纯的文档文字，改示例要连带改这些夹具，一并留给后续任务。
已验证（没改代码，只是确认基线）：`tests/tools/test_dslagent_v3.py` 的
「v3 假模型整条流程跑通」268 项全过，当前 `tools/dslagent` 基线是绿的，
后续任务可以放心在这个基线上继续改。

**R3（tools/dslagent/verbs 的返回键，已做）**：只改**返回键**（字段名），
「是/否」值不动（C1/C2 遇到的那批 29 个文件的布尔值问题留给专门任务，
没有在 R3 里碰）。改了 `verbs/dslproj/defs/`（加载检查、比对约定、跑用例）、
`verbs/newproj/defs/`（参数核对、校验实体、校验清单、核对规则；`校验分层清单`
是文档标注的旧动词、layered.py 已不用、只剩一条「ok=否」的兼容测试，没改）、
`verbs/v3/defs/` 下近 20 个 Python 动词与 4 个 .zs 动词（做一个模块、做模块组、
规划一份、规划到通过）的返回键；`做模块`/`全量回归`/`接口冒烟` 三个直接转发
`tools/dslagent/v3/modrun.py`/`regress.py` 结果的动词，在动词外壳这层加了
翻译（没有改 `v3/*.py` 内部实现的键，那些不算「verbs 的返回键」）。同步改了
全部消费点：`packs/dslproj/prompts/example.zs`、`packs/newproj/newproj_split.zs`、
`tools/dslagent/layered.py`/`modbuild.py`（这两个文件按动词名直接查表调用
`校验实体`/`核对规则`，之前没注意到，第一轮测试跑挂才发现）、以及
`tests/tools/test_dslagent_{dslproj,newproj,v3,layered}.py` 里直接走引擎或
直接 import 动词模块验证返回值的断言。本条新增的对照项（补进下面这张表、
风格与已有一致）：

| 旧（中文） | 新（英文） | 旧（中文） | 新（英文） |
|---|---|---|---|
| 一致/差异 | consistent/diffs | 全过/失败/总数 | all_passed/failures/total |
| 按模块 | by_module | 检查数 | checked |
| 实体数 | entity_count | 模板 | template |
| 功能 | features | 调用上限 | call_limit |
| 角色 | roles | 角色模板 | role_template |
| 解析 | parsed | 未实现/未实现列表 | unimplemented/unimplemented_list |
| 改了/没变 | changed/unchanged | | |
| 删了 | removed | 写了 | written |
| 新建/已有/新建数 | created/existing/created_count | 花费/调用/轮/记录目录/秒 | cost/calls/round/log_dir/secs |
| 次数（规划一份的重试计数，区别于「轮数」=rounds） | attempts | | |

没碰、按规则排除的：`功能`/`角色` 等顶层键下面**嵌套**的字段（如每个功能项
的 `名`/`sql`/`接口`/`规则`/`界面`、接口项的 `角色`/`路径`/`动作`）——那是
模型 JSON 回复本身的 schema（`newproj` 的 split 模板提示词定的），留给
R4（提示词/模型回复键）；`tools/dslagent` 内部 `c.log(...)` 记的账本/日志
字段（如 `全局检查.py`、`检查规划.py` 里 `c.log("规划", ..., 条数=.., 问题=..)`）
不算「verbs 返回给脚本的结构」，原样留着，测试里读 `ctx.records` 的断言
不用改。

测试：`tests/dsl/*`、`tests/http/*`、`tests/gen/*` 全绿；
`tests/tools/test_dslagent_*.py`（28 个）+ `test_obatch.py` + `test_cbatch.py`
全绿（含 `test_dslagent_v3.py` 317 项、`test_dslagent_modbuild.py` 268 项、
`test_dslagent_layered.py` 168 项）。

**R4（dslagent 提示词与 .zs 流程的数据键，部分完成）**：做了范围里能独立核实、
消费点可控的一块，`packs/newproj` 整个族没碰（见下「没做完的」）。

已改（模型回复 JSON 的键，解析端兼容旧键）：
- `v3/prompts/audit.md`：`{"问题","涉及模块","依据"}` → `{"issue","modules","basis"}`；
  `v3/issues.py`（`parse_model_issues`〔已删，改由 `v3/audit.py` 的 `merge` 收口〕/`format_issue`/`parse_issues`/`program_items`/
  `run_logic_checks` 的内部条目表示同步改成 issue/modules/basis，`parse_model_issues`
  与 `run_logic_checks` 对模型回复两种键都认；持久化的问题清单 .md 文件里「涉及模块：」
  「依据：」是给人看的展示文字，不是键名，没有改）。
- `v3/prompts/logic_check.md`：`{"问题","依据"}` → `{"issue","basis"}`，消费点同 issues.py。
- `v3/prompts/review.md`：`{"通过","问题列表"}` → `{"passed","issues"}`；
  `v3/planning.py` 的 `parse_review`/`review()` 内部表示同步改成 passed/issues
  （两种键都认），`verbs/v3/defs/复核约定.py` 读 `r["passed"]`/`r["issues"]`；
  `ctx.log(...)` 记账用的 `状态=`/`通过=`/`问题=` 关键字参数名不算数据键，没有改
  （只是取值的来源从 `got["问题"]` 变成 `got["issues"]`）。
- `v3/prompts/classify.md`：`{"标签"}` → `{"label"}`；`v3/prompts/prescreen.md`：
  `{"通过","理由"}` → `{"passed","reason"}`（这两个角色是 F 任务新加的通用助手，
  当前没有 Python 消费点读这两个字段，改提示词不牵连代码）。
- `agents/bound_judge.md`：`{"条目序号","判定","依据"}` → `{"item","verdict","basis"}`
  （枚举值「代码错」「期望写错」不改）；`verify/bound_table.py` 的 `parse_judge` 两种键都认。
- `agents/fix.md`、`agents/bfix.md`、`agents/sub.md`、`agents/sub_tool.md`、
  `agents/README.md`、`packs/dslproj/prompts/fix_system.md`：回复格式里的
  `结果/状态/原因/思路` → `result/status/reason/thought`（顶层）；这几个 agent 本来就走
  `tools.dsl_task.check_reply`/`json_repair.normalize_keys`（R1 加的兼容层），改的只是
  提示词文字，不是解析代码；嵌套在 `结果`/`result` 里的 `说明`（补改的记账字段，R1 已经
  定了不动）、`edits`（本来就是英文）没有改。
- 发现并修了两处 R1 之后没跟上的**失真教学文档**（规划模型读到的提示词，不是代码，
  但教的写法与改名后的真实返回键不一致，模型照抄会生成跑不起来的脚本）：
  `agents/shared/verbs.md`、`packs/dslproj/prompts/verbs.md` 文档的 `派任务`/`并行派任务`
  返回 `{结果,状态,原因}` → `{result,status,reason}`（R1 只改了引擎和消费点，没改这两份
  教模型怎么写 .zs 的速查文档）；`packs/dslproj/prompts/verbs.md` 顺手连带修了
  `加载检查`/`比对约定`/`跑用例` 的文档返回形状（R3 改引擎时没同步这份文档）；
  `agents/shared/cheat.md` 的 `执行 _plan/x.zs` 后 `{r.状态}{r.原因}{r.停在}` →
  `{r.status}{r.reason}{r.at}`；`agents/shared/plan_rules_code.md` 的 `{r.结果}` → `{r.result}`
  （两处）。

没做完的（已查清范围，留给后续任务）：
1. `packs/newproj/prompts/` 下十余份要求模型回 JSON 的提示词（`sys_plan.md`、
   `sys_llayer.md`、`sys_lfiles.md`、`sys_lfplan.md`、`sys_mplan_{ent,flow,iface,sql,ui}.md`、
   `sys_frule.md` 等），每份字段名都是中文（如「功能/角色/规则/界面」及更深的嵌套字段），
   消费点是 `verbs/newproj/defs/` 下对应的校验/解析动词与 `scaffold`/生成代码——这些字段同时
   是 newproj 生成管线的内部协议，改一处牵全链，量级比本条已做的部分大得多，没有碰，
   连同 C2 留的「29 个「是/否」字符串返回」一起留给专门任务。
2. `agents/bound_table_fill.md` + `agents/shared/plan_rules_code_table.md`（「code」资料包
   的「期望表」协议：模型回 JSON 数组，字段「规则/函数/参数/断言/期望/期望包含/期望异常/文件」，
   外加 11 种断言算子「条数/都不含/都含/有含/都匹配/字段都在/有序/行号连续/不抛异常/同改前/
   类型」）——消费点是 `verify/bound_table.py`/`verify/asserts.py` 整套断言判定逻辑，字段名同时
   是内部表示（`bound_table.py` 里 `k['rule']`/`k['key']`/`k['args']` 等已经是英文，但模型侧
   协议还是中文），改动面和历史分量（依据 `/workspace/dslagent_exp/bound_code4/REPORT.md` 的
   实测调参）都不小，没有碰。
3. `verify/code.py`/`fix.md`/`bfix.md`/`fix_system.md` 里嵌套在 `结果`/`result` 内的 `说明`
   字段——R1 已经定性为「补改自己的记账字段」不在范围内，本条延续同一判断，没有改。

## 命名约定收尾（R6，已完成）
数据键改英文覆盖：引擎终止/派任务/并行执行（R1）、`tools/dslagent/verbs` 返回键
（R3）、v3 提示词与 agents 通用回复格式（R4 部分）。`verbs/db`/`common`/`http`/`quiz`
核实后不需要改（R2，见上「还没覆盖的范围」已更正说明）。布尔值、状态/枚举值、
业务函数名、语法层关键字不在改名范围内——C1 当初把 5 个动词改成真布尔已由 R5
退回「是/否」字符串。上面「最终对照表」「回复格式键」「kg 别名 / 为 kg 保留的中文
清单」是这轮改名的权威总结；「还没覆盖的范围」列的是真实剩余项（`packs/newproj`
提示词协议、`code` 资料包期望表协议），留给专门的后续任务，不在本次范围内。

---

## 五、动词包

```
用包 common          取字段 计数 列表长度 当前时间（相加 / 算比例 是旧写法，请用 计算）
用包 quiz            挑题 挑题号 取题 判题 列课程 列考点 题目数 …
用包 japanese        假名进度 含日语 假名统计 取假名行 列假名行
用包 data            读CSV 读文本行 读YAML 写JSON 写JSONL 删文件 移动文件 列文件 …
用包 db              查询 查一行 查一值 写库 列查询 表结构 事务三件套
用包 http            消息 状态 响应 消息流 表格
```

算术用引擎语句 `设 n = 计算 {a} + 1`（加减乘除、括号、`四舍五入(x, 位数)` 等；百分比：
`计算 四舍五入({对} * 100 / {总})`，总数可能为 0 时先判断）。`当前时间 [日期|时间戳]` 取本地
时间；环境变量 `DSL_NOW`（如 `2026-10-19 12:00:00`）设了就返回它，测试用。

`http` 只在 HTTP 请求里能用，`dsl_run` 里调会返回「不在请求里」。

### 写一个新动词

`verbs/<包名>/_verbs.py`：

```python
def register(reg, workspace):
    @reg.verb("这个动词干什么的")
    def 动词名(参数一: str, 参数二: str = "") -> str:
        return "结果"
```

或者 `verbs/<包名>/defs/动词名.py` 单文件。目录名用英文，文件名用
中文——动词名要出现在 `.zs` 里，目录只有 Python 碰。

### 动词的参数：必填 / 可选 / 默认值 / 键=值

`.zs` 动词文件头声明：

```
# 参数：种类 需求? 最多=3 模型=sonnet 停在?
```

- 分隔符：空白、顿号、逗号、全角逗号都行。
- `名` 必填；`名?` 可选，不传为空串；`名=值` 有默认值（字面文本，不展开
  变量，值里不能有空白和顿号逗号）；`名=` 等同 `名?`。
- **兼容**：声明里没有任何 `?` 或 `=` 的旧文件保持旧行为（少传为空、不报错）；
  有任意一个就按新规则（裸名必填，缺了报错）。
- Python 动词取函数签名：没有默认值的必填，有默认值的不传就用函数自己的默认。

调用时位置参数和 `键=值` 可以混用（位置参数写前面；写在 `键=值` 后面的位置参数依次填
还没给的参数）：

```
词汇讲解 {词表} 级别=N5
设 r = 取任务 重要 停在={step}
```

- 一个词形如 `键=值` 且「键」是该动词声明的参数名才当关键字参数；否则按位置
  参数原样处理（`计算 a=b` 这类不受影响）。
- 同一参数给两次、必填没给、位置参数多于声明 → 运行前（加载检查）或运行时报错，
  信息里有动词名、参数名、调用行号和声明所在文件行号。
- `键=值` 的值整个是 `{变量}` 时保留结构（列表 / 对象）。
- list_verbs 里签名显示成 `<种类> <需求?> <最多=3>`。

### 并行执行：同时跑一组子脚本

```
用包 common
设 rs = 并行执行 {jobs} 并发=3
遍历 r 于 {rs}
  如果 {r.状态} 不等于 成功
    打印 {r.脚本} 没做成：{r.原因}
  结束
结束
```

- `jobs` 是列表，每项是一个子脚本：文本 `"脚本名 键=值 键=值"`（同「执行」，值里不能有空格），
  或对象 `{"脚本": "名", "参数": {"键": "值"}}`（值可以带空格、换行、结构）。
- 脚本名先当工作目录里的 `.zs` 文件找，找不到就当脚本动词（`.zs` 动词）的名字，参数按动词声明绑定（默认值生效）。
- 每项独立作用域、独立子引擎（共用客户端、动词表、预算），等全部结束才返回；并发缺省 3，范围 1–8。
- 返回列表，顺序同输入，每项 `{脚本, 参数, 状态, 原因, 停在, 返回}`：正常结束或 `返回` 了 → 状态 成功，
  `返回` 为返回值（没写 `返回` 就是输出文本）；子脚本 `终止` 了 → 状态是它的状态（成功 / 失败 / 超出预期）；
  脚本出错（读不到文件、动词报错、找不到子脚本）→ 状态 失败，原因是错误的第一行。**单个失败不影响别的项**，也不让整个脚本崩。
- 预算用完时各项按「终止 超出预期」结束，调用方的下一条语句照样终止。

### 脚本动词里的「终止」往外传

`.zs` 动词（`# 参数：…` 那种）里写 `终止`：
- 调用方**没接结果**（`做模块组 graph`）→ 终止接着往外传，结束调用方（再往上同理，到顶层脚本为止）。
- 调用方**接了结果**（`设 r = 做模块组 graph`）→ 拿到 `{状态, 原因, 停在}`，自己决定接着走还是 `终止 {r.状态} {r.原因}`。
- `执行 子.zs` 不变：只结束子脚本，要接结果自己判断。

---

## 六、HTTP 接口

```
服务 8091-8099              端口范围，命令行 --port 优先

接口 POST /drill/answer 动作 submit
  用包 common quiz http
  设 结果 = 判题 content/n2n3/题库 {会话.题号} {answer}
  消息 批改 {结果} ok
结束
```

```
py -m tools.dsl_http --list        只看有哪些接口
py -m tools.dsl_http --mock        假客户端跑
```

请求体的字段直接是变量（`{answer}`），GET 的查询参数也是。
会话状态是 `{会话.xxx}`，按 `learner` 分文件，脚本跑完自动存回。

**两种返回**：

```
返回 {"code":0}             通用，像 Flask 的 return，立即结束
消息 批改 {结果} ok          配套 .ui 前端，塞完接着跑
```

同一块里混用的话「返回」赢。

---

## 七、周边

### .entity → 建表

```
实体 learner 学习者
  字段 code 文本 必填 学号
  字段 level 枚举 N5,N4,N3,N2,N1 级别
  字段 started 文本 必填 默认 now 开始于
  主键 code
结束
```

```
py -m tools.gendb --check           只校验
py -m tools.gendb --create --demo   建库并塞假数据
```

类型：文本 长文本 整数 小数 日期 布尔 枚举
旗标：必填 唯一 索引 系统 级联删除
- `系统`：值由系统定。新建一律写默认值（客户端传什么都不算），gen 的修改接口不改它，表单里不出现，列表/详情照常显示；必须带 `默认`。自己写的 .zs 仍可用自己的 sql 改它（状态流转接口就这么做）。
  `字段 status 枚举 草稿,已提交 必填 默认 草稿 系统 状态`
- `级联删除`：只能写在带 `关联` 的字段上，建表时外键为 ON DELETE CASCADE，删父记录连带删子记录，可多层；没写的关联仍是 RESTRICT（被引用时删除被拒）。只对新建的库生效，已有的库不会迁移（要生效需重建库）。
  `字段 project_id 整数 必填 索引 关联 project 项目 级联删除`
- 这两个旗标可写在标签前或后。

其它：`关联 <实体>`、`默认 <值>`、`主键 a b`

**跨存储引用不写「关联」**——题号指向 jsonl 题库、节点指向 kg.db，
那里没有表可引用，写了会生成建不出来的 schema。

### .ui → 界面

```
界面 表单 文章编辑
  分组 主体 竖排 间距 12px
    全部字段 article 除 created_at
    字段 author.name 作者
  结束
结束
```

`全部字段 <实体>` 编译时展开，实体加字段界面跟着变。
`字段 <实体>.<字段>` 带实体名，跨实体重名时用。

### gen → 从实体生成一套

```
py -m gen --all --check            自检
py -m gen article --write          写到 gen/out/
py -m gen --web                    网页界面
双击 gen/app.pyw                   生成器窗口
双击 gen/edit.pyw                  .ui 编辑器
```

一个实体出七个文件：五条 SQL、一段 `.zs`（五个接口）、一段 `.ui`
（三个界面）。生成什么在 `gen/templates/<模板集>/` 里，换套模板换个
形状。

---

## 八、排查

```
dsl_help                     语法说明（dsl.py 的 docstring）
list_verbs                   有哪些动词，按包分组
run_tests                    147 项引擎测试
tool_call name=ui.check      检查 .ui
tool_call name=entity.check  检查 .entity
file.show path=x around=y    看文件的某一段
```

改了 `tools/` 下的代码之后，`tool_call` 或 `agent_send` 带
`reset=True` 重新加载，不用重启服务器。
