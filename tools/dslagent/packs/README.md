# 资料包（pack）：怎么写一个新包

v2 核心（`v2.py`）只管「规划 .zs → 执行 → 验收 → 补改」这条流程，不知道任务是什么。一类任务要的全部差异，都由一个包声明：

| 要声明的 | 名字 | 核心怎么用 |
|---|---|---|
| 资料 | `materials(task, project, scope) -> {"text", "记录"}`（可选） | `text` 拼进规划的 user；`记录` 并进 result.json 的 `v2.*`。确定性，不调模型 |
| 动词 | `VERBS`（动词名）、`VERB_PACKS`（脚本里「用包」可写的包，缺省 `("code",)`）、`WRITE_VERBS`（写 / 删文件的动词，⊂ VERBS）、`GATED_VERBS`（可选：结果不影响走向时只给占位、验收统一跑的动词） | 语句 / 动词白名单 = `plan.BASE_VERBS` ∪ `VERBS`（`packs.verbs_of`），`用包` 白名单 = common text + `VERB_PACKS`（`packs.use_of`） |
| 验收 | `accept(project, ctx) -> {"通过", "问题", "摘要"}`，或 `verifier()` 返回完整验收对象 | 计划执行完（`终止 成功`）后验收；没过派 1 次补改，补改后再验一次 |
| 范围 | `scope_for(task, project, given) -> [路径…]`、`STRICT_SCOPE` | 允许写 / 删的路径；命令行 `--scope` / `run(scope=)` 优先；`STRICT_SCOPE=True` 时写类动词在写之前统一按它拦（见下） |
| 规划说明 | `PLAN_SYSTEM`（字符串或 `f(engine)`），或 code 式的 `PLAN_RULES` / `PLAN_RULES_END`（`agents/shared/plan_rules_<KEY>*.md`） | 整份规划 system：这类任务的要点 + 示例 .zs |
| 计划检查（可选） | `plan_problems(main, body, cl, generic) -> [问题…]` | 白名单检查之后、假模型空跑之前；`generic` 是核心已查出的通用问题（如缺 预算） |
| 其它（可选） | `files(project)`、`TASK_DESC`、`PACK_DESC`、`GATE_NOTE` | `files`：要做快照的文件（缺省 = 项目里的文本文件） |

声明合格与否由 `packs.validate(pack)` 检查（缺 NAME / VERBS / 验收 / 规划说明、动词不存在、WRITE_VERBS 或 GATED_VERBS 不在 VERBS 里、VERB_PACKS 里的动词包不存在……），`v2.run` 启动时调用，不合格直接判失败、0 次模型调用。

## 步骤
1. **登记**：`packs/__init__.py` 的 `REGISTRY` 加一行 `"名": "tools.dslagent.packs.名"`（模块或子包）。cbatch 的 `dsl_options.pack`、命令行 `--pack`、`run_task(pack=)` 都按这个名字取。
2. **动词**：要新动词就放进 `tools/dslagent/verbs/<包名>/`（`_verbs.py` 照抄 dslproj 的，`defs/<动词>.py` 一个动词一个文件，沙箱根是引擎工作目录 `WORKSPACE`）；
   空跑（计划检查）时动词要给结构合法的占位结果（`current_engine().dry_run`），别碰项目。读 / 搜 / 改 / 写文件直接复用 code 包的动词（`VERB_PACKS = ("code", "你的包")`）。
3. **验收**：最简单是写 `accept(project, ctx)`：`ctx = {task, scope, stage("验收" | "补改后"), out, changed, base, cur, main}`，返回 `{通过, 问题: [文字…], 摘要}`。
   核心用 `verify/simple.py` 把它包成完整验收：有问题时补改入参 = 任务原文 + 问题 + 范围内现有文件（或你的 `fix_input(project, ctx, probs)`），补改 system 取你的 `FIX_SYSTEM`（缺省通用文本），回复 `{结果:{edits:[{file, old, new}]}, 状态, 原因}`，edits 能套就套（套用同样过范围拦截）。
   要边界复核等更复杂的验收就写 `verifier()`，返回实现了 `verify/__init__.py` 接口的模块（code 就是这样：`verify/code.py`）。
4. **范围**：`scope_for` 返回 glob 列表：`a/`（目录前缀）、`a/b.py`（精确文件）、`routes/x*`（含 `* ? [` 的按 glob 匹配整条相对路径，`*` 可跨目录）。
   - `STRICT_SCOPE = True`：核心在 `v2.run` 里 `scope.activate(范围)`，写类动词（经 `reason.check`）和补改套用（`verify.code.apply_edits`）写 / 删之前先问 `scope.guard(相对路径)`，范围外的整体被拒（`ok=否`，msg 以「范围拦截」开头），模型当场看到原因；范围同时写进环境变量 `DSLAGENT_SCOPE_GLOBS`，子进程（dslmcp 的 tool 模式）从那里读。规划时的假模型空跑也按它拦。
   - 不声明（code）：只做事后闸——执行 / 补改后对比快照，范围外的改动恢复成改前内容并要求补改（旧行为，`--scope` 一直是这样）。事后闸对两种包都在，作为兜底。
5. **规划说明**：`PLAN_SYSTEM` 写这类任务的角色、可用动词表、要点和一份**能通过检查的**示例 .zs（单测里把示例喂给 `v2.check`，白名单 / 改法 / 空跑都要过）。
6. **测试**：照 `tests/tools/test_dslagent_packs.py`（接口）、`test_dslagent_dslproj.py`（一个完整的包）写：声明校验、白名单、范围拦截、验收、假模型整条流程。

## 现有的包
- **code**（`code.py`）：改代码仓库、跑测试。资料 = 文件大纲（`plan_outline`）；动词 = code 包（列文件 搜索代码 读片段 运行代码 改文件 跑测试 写文件 删文件 改模块名 查引用）；
  验收 = `verify/code.py`（全量测试、清单、旧写法残留、DSL 文件检查、边界复核）；`GATED_VERBS = ("跑测试",)`；无默认范围；规划说明 = `agents/plan.md` + `plan_rules_code*.md`。
- **dslproj**（`dslproj/`）：做 DSL 项目里的一个模块。见下。
- **newproj**（`newproj/`）：新建项目的固定模板，不走规划（`v2.run_newproj`），只用 `EXTRA_VERBS` / `EXTRA_PACKS` / `files` 这几个旧名字。

## dslproj
**任务**：任务文本里有一行 `模块 <名>`（其余是补充说明）；项目里有 `contracts/<名>.md`。入口：

    python -m tools.dslagent run --pack dslproj --project DIR --task-file F --out DIR      # F 里写「模块 graph」
    entry.run_task(DIR, "模块 graph", "dslproj")                                              # → {状态, 原因, 花费, 记录目录, 改动文件}
    python -m tools.dslagent.packs.dslproj.cases --project DIR --module graph                  # 只跑用例（unittest 风格输出，退出码 0 = 全过）

**项目布局**：`contracts/<模块>.md`（约定，冻结，不在范围内）、`entities/<模块>.entity`、`services/<模块>.zs`、`routes/<模块>*.zs`（文件名以模块名开头）、`queries/<模块>_*.sql`、`tests/<模块>_*`。
范围 = 后五类（不含 contracts/、别的模块的文件）。

**约定格式**（`contract.py` 文件头有带注释的完整示例）：

    模块 progress
    依赖 graph                                  # 无依赖写「依赖 无」
    ## 表            表 answer [学习记录] / 下面每行「字段 类型 说明」   # 拥有学习者真实记录的表标「学习记录」（只加不重建，见 tools/migrate.py）；比对时只看每个表在 entities 里有同名实体
    ## 函数          [公开] 函数 名 入参… （入参末尾 ? = 可选） / 下面 返回 … / 报错 4xx 文字 / 伪代码 …（可多条；跨模块调用写 调用 模块.函数）
    ## 接口          POST /progress/answer -> 记作答       # 方法 路径 -> 本模块公开函数
    ## 用例          每个公开函数至少一条

**用例形式**（`## 用例` 下，每个用例在空库上单独跑）：

    用例 记作答_累计
      先 数据 point code=P1 title=一次函数       # 直接往表里插一行（可以是上游模块的表）
      先 调用 记作答 learner=u1 point_code=P1 correct=1   # 或调公开函数造前置（[模块.]函数）
      先 文件 uploads/a.md 内容=第一行\n第二行    # 跑的时候在临时项目里造出这个文件（相对路径、不含 ..）；调用时 file_path=uploads/a.md 直接传；跑完删除
      调用 记作答 learner=u1 point_code=P1 correct=0      # 恰好一条，本模块的公开函数；值里不能有空格，「空」= 空串
      得 total=2 right=1 score=50               # 返回对象的字段（数字按数值比）；或「得 为空」「得 有返回」
      库 answer 共 2 行                          # 可多条：「库 表 共 N 行」「库 表 含 k=v …」「库 表 无 k=v …」
    用例 记作答_没有知识点
      调用 记作答 learner=u1 point_code=NOPE correct=1
      报错 404                                  # 期望业务错误码（和「得」二选一）

**跑用例**（`cases.py`）：项目拷到临时目录（不改项目）；每个用例新建 `app.db`（按 本模块 + 上游模块 的 `entities/*.entity` 建表，缺上游实体文件会说明）→ 先 → 调用（DSL 引擎跑
`调用 模块.函数 k=v 出错时 e`，`services/` 整个目录加载）→ 核对 得 / 报错 / 库；环境变量 `DSL_NOW` 固定为 `2026-01-01 09:00:00`（`--now` 可改），所以 `当前时间` 确定；只依赖本模块和它的上游，可单独跑一个模块。
**比对约定**（`project.compare`）：`services/<模块>.zs` 的模块名、依赖、每个约定函数（公开与否、入参顺序与可选）、没有多出来的公开函数；接口（方法 + 路径都在，且只调约定里那一个函数、没有多余接口）；约定里的表在 entities 里都有同名实体；表带「学习记录」标注时 routes/ 下要有「迁移 只加」声明（v3 的生成骨架会自动写出 `routes/_project.zs`）。
**验收**（`accept`）：`加载检查`（`loadcheck.check_project` 里属于本模块 services / routes 文件的问题）无错 + 比对约定一致 + 本模块用例全过；任一不过派 1 次补改，补改后再验。
**动词**（`verbs/dslproj/`）：`加载检查 模块`、`比对约定 模块`、`跑用例 模块`，规划脚本里在套完改法后调，自查三项。
**资料**：本模块约定全文、上游模块公开函数头（含返回 / 报错，不含伪代码）、本模块现有文件（骨架）、DSL 项目写法速查（`prompts/syntax.md`）。
