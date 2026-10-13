# dslagent 的 agent：一个 agent 一个 Markdown 文件

人读的内容（system 提示词、用什么工具、几轮、回复什么格式、失败了怎么办、user 由谁拼）都在这个目录；
`agents.py` 只留 Python 才能表达的东西（user 拼装函数、解析器、重试次数）。解析 / 展开 / 选变体的代码在 `promptfile.py`。

## 文件格式
```
---
名称: plan                       frontmatter：每行「键: 值」
步骤: plan                       models 的键（plan / sub / fix / bound）
工具: 只读dsl；grok：grok自带只读   无 / 只读dsl / grok自带只读 / 可写dsl；「；引擎：值」给某个引擎换
最多轮数: 12；grok：20            --max-turns；没工具的是 1
回复格式: zs（…）                 zs（.zs 计划）/ json（{结果,状态,原因}）/ code（python 代码）
失败时怎么办: …最多 2 次…          白话；「最多 N 次」要和 agents.py 里的 Retry 次数一致（加载时核对，不一致报错）
输入: …                          user 提示词由谁拼、包含什么
---

正文 = 完整的 system 提示词（逐字发给模型）
```
- 正文开头是 frontmatter 之后空一行；文件末尾那一个换行不算提示词（提示词末尾要换行就多空一行）。
- 单独一行 `{{插入 路径}}`：换成 `shared/` 下该文件的原文（`lib/…` 指 `tools/dslagent/lib/`；路径里的 `{包}` 换成资料包名，缺省 code）。
- 正文只有一行 `{{沿用 别的.md}}`：整个用那个 agent 的 system（plan_fix 就是这样沿用 plan）。
- `## 变体：引擎名`：该引擎专用的改写，里面成对写 `### 原文` / `### 改成`，把渲染后提示词里的原文换成新文（找不到原文直接报错，防止悄悄失效）。
  目前只有 plan.md 的 `变体：grok`（grok 没有 dsl 工具，读代码的两处说法不同）；claude / codex 用正文原样。
- `## 模板：名字`：给代码拼 user 用的模板，`str.format` 填 `{占位}`（字面花括号写 `{{` `}}`）。目前只有 plan_fix.md 的「用户提示词」。

## 文件一览
| 文件 | 干什么 | 步骤 | 工具 |
|---|---|---|---|
| `plan.md` | 规划：读任务和文件大纲，按需读代码，输出 .zs 计划 | plan | 只读 dsl（grok：自带只读） |
| `plan_fix.md` | 计划没过检查时，带问题重写脚本（system 同 plan，user 是「模板：用户提示词」） | plan | 同 plan |
| `sub.md` | 子任务（派任务 / 问JSON）json 模式：只回 JSON，改动由程序套 | sub | 无 |
| `sub_tool.md` | 子任务 tool 模式（dsl_options.subtask=tool，仅 claude）：用可写 dsl 工具自己读改 | sub | 可写 dsl |
| `fix.md` | 验收有缺口时的补改：回 edits | fix | 无 |
| `bound.md` | 边界复核：写 3–5 个 unittest 用例 | bound | 无 |
| `bfix.md` | 边界用例没过时的补改 | bound | 无 |

`shared/`：`cheat.md`（DSL 速查）、`verbs.md`（可用动词）、`tips.md`（写法要点全文，旧路径用）、`tips_plan.md`（规划用的 4 条写法要点）、
`rules_head.md` / `rules_stop.md` / `rules_out.md`（通用规划规则）、`plan_rules_code.md` / `plan_rules_code_end.md`（code 资料包专属规则）、`see.txt`（user 里「见系统提示」一句）。

## 流水线（按顺序）
1. **规划**（`plan.md`）：user = 任务原文 + 文件大纲（`v2.plan_user_read`；大纲由资料包 `plan_outline` 确定性产出，不含代码）。模型用只读工具自己读代码，输出完整 .zs。空回复 / 引擎出错 / 保险触发就再问同一个问题，最多 2 次。
2. **检查**：程序做（白名单、有 预算、资料包专属检查、假模型空跑），不调模型。没过就用 `plan_fix.md` 带问题重写 1 次；仍不过整次回滚、判失败。
3. **执行**：引擎跑计划。计划里的 派任务 / 并行派任务 / 问JSON 调子任务：默认 `sub.md`（json 模式，回复不合格带问题重问 1 次）；`dsl_options.subtask=tool` 且引擎是 claude 时用 `sub_tool.md`（两次尝试，用尽退回 `sub.md`）。
4. **验收**：程序跑测试、找缺口（不调模型）。有缺口就派 `fix.md` 补改 1 次，补改后再验收一次。
5. **修**：`fix.md` 回 `{结果:{edits:[…],说明},状态,原因}`，程序套 edits；整体套不上就逐条套。
6. **边界复核**（可选）：`bound.md` 按任务原文 + diff 写边界用例并跑；失败就带失败信息派 `bfix.md` 补改 1 次，再跑用例和全量测试；仍失败或补改弄坏现有测试（撤回补改）都判「超出预期」。

## dsl_options 怎么作用到这些文件
- `models`：`{plan, sub, fix, bound}` 各步用哪个引擎 / 模型（`engines.step_of`）。文件里的「步骤」就是这里的键：plan.md、plan_fix.md 用 `plan`；sub.md、sub_tool.md 用 `sub`；fix.md 用 `fix`；bound.md、bfix.md 用 `bound`。
  引擎是 grok 时：plan / plan_fix 的工具、轮数取 frontmatter 里「grok：…」那一项，system 套 `变体：grok`；codex 与 claude 用同一份正文。
- `planner`（DSLAGENT_PLANNER=v2）：走 v2 流水线（上面 1–6）才用这些文件；缺省的旧路径用 `prompts/legacy/`。
- `subtask`：`json`（缺省）用 sub.md，`tool` 用 sub_tool.md。
- `pack`（DSLAGENT_PACK，缺省 code）：决定 plan.md 里 `{{插入 plan_rules_{包}.md}}` 插哪套资料包专属规则，以及大纲 / 验收怎么做。新增资料包要加 `shared/plan_rules_<包名>.md` 和 `plan_rules_<包名>_end.md`（包名取资料包的 `RULES_KEY`，没有就取 `NAME`）。

## 改提示词的注意
- 改完跑 `tests/tools/test_dslagent*.py`；改 plan.md 正文时留意 `变体：grok` 里的「原文」是否还在（不在会直接报错）。
- 逐字节核对：把各 agent 的 system 导出存档，改前改后 `cmp`。
