# dslagent 提示词文件

提示词文本都在这个目录下，UTF-8、LF；代码里的原常量名（`prompts.CHEAT`、`v2.SUB_SYS`、`packs.code.PLAN_RULES`、
`verify.code.FIX_SYS` 等）保持可用，加载时从这里读（`tools/dslagent/promptfile.py`，按相对路径读、带缓存，文件缺失会报出完整路径）。
`lib/示例_分支规划.zs` 仍在 `tools/dslagent/lib/`，规划 system 的末尾读它。

## 加载与占位约定
- `promptfile.text(rel)`：文件原文，逐字返回（不去首尾换行；文件末尾有没有换行就是提示词末尾有没有换行）。
- `promptfile.tpl(rel, **kw)`：文件名带 `.tpl` 的是模板，用 Python `str.format` 填 `{名字}`；文件里要写字面花括号时写 `{{` `}}`。
  填进去的值不再解析，所以值里有 `{x}` 没问题。非 `.tpl` 的文件按原文用，里面的 `{task}`、`{e1}` 之类是给模型看的 DSL 写法，不是占位。
- `promptfile.js(rel)`：JSON 文件。

## 规划 system（`v2.plan_system`）的拼接顺序

先由 `v2._base_system` 拼出底稿（下面 1–6），再按下面「读代码改写」改成实际发给模型的 system。各 agent（规划 / 子任务 / 补改 / 边界）用哪个提示、哪个 user 拼装函数，见 `agents.py`。

1. `plan_intro.tpl.txt`（占位 `{TASK_DESC}` `{PACK_DESC}`，来自资料包）——末尾自带空行
2. `cheat.md` + 空行
3. `verbs.md` + 空行
4. 「写法要点（节选）」：`tips_head.txt` + 从 `tips.md` 里按 `v2.plan_system` 的 `keep` 列表筛出的几条（筛选逻辑在代码里，用 `- ` 分条）+ 空行
5. 规划规则 `v2.plan_rules`，各段之间换行：`rules_head.md`、`packs/code/plan_rules.md`、`rules_stop.md`、`packs/code/plan_rules_end.md`、`rules_out.md`；后面空行
6. `plan_example_head.txt` + `lib/示例_分支规划.zs`

读代码改写（`v2.read_system`）：在上面的底稿基础上，先把第 1 项里的 `plan_intro_cut.tpl.txt` 那句换成 `plan_intro_read.tpl.txt` 那句
（底稿里必须找得到，找不到断言报错），再按 `read_subs.json` 的 `claude` 列表逐项「原文 → 新文」替换（原文必须存在，否则断言报错）；
引擎是 grok 时，下标在 `grok` 里的项改用 grok 那一对。新文里的 `{READ_TAIL}`、`{READ_TAIL_GROK}` 分别换成 `read_tail.txt`、`read_tail_grok.txt` 的内容。

规划 user 不在文件里（`v2.plan_user_read`：任务原文 + 文件大纲）。重写计划的 user 是 `fix_prompt.tpl.txt`。

## 文件一览

### 通用（规划 / 重新规划，`prompts.py`、`v2.py`；v2 和旧路径共用）
| 文件 | 内容 | 用在哪 |
|---|---|---|
| `cheat.md` | DSL 速查 | 规划 system（上面第 2 项）；`legacy.prompts.SYSTEM` |
| `verbs.md` | 可用动词 | 规划 system 第 3 项；`legacy.prompts.SYSTEM` |
| `tips.md` | 写法要点全文 | 旧路径 `legacy.prompts.SYSTEM` 用全文；`v2.plan_system` 只取节选 |
| `plan_intro.tpl.txt` | v2 规划 system 开头说明，占位 `{TASK_DESC}` `{PACK_DESC}` | 规划调用 |
| `plan_intro_cut.tpl.txt` / `plan_intro_read.tpl.txt` | 读代码改写时要去掉的那句 / 换成的那句，占位同上 | `v2.read_intro_cut` |
| `tips_head.txt`、`plan_example_head.txt` | 写法要点（节选）、示例的小标题 | 规划 system 第 4、6 项 |
| `rules_head.md` `rules_stop.md` `rules_out.md` | 通用规划规则的开头 / 终止 / 输出要求 | 规划 system 第 5 项 |
| `read_tail.txt` / `read_tail_grok.txt` | 「用 dsl 工具读」说明 / grok 版限读说明 | `read_subs.json` 的 `{READ_TAIL}` 占位 |
| `read_subs.json` | `{"claude": [[原文, 新文], …], "grok": {"下标": [原文, 新文]}}`，读代码改写的替换表 | `v2.read_system` |
| `sub_sys.txt` | 子任务（派任务）的 system | 子任务调用 |

### 旧路径（legacy/，`legacy/prompts.py`，文件在 `prompts/legacy/`）
| 文件 | 内容 |
|---|---|
| `legacy/system.tpl.txt` | 修 bug / 任务路径规划 system，占位 `{CHEAT}` `{VERBS}` `{TIPS}` `{SKELETON}`（`legacy.prompts.SYSTEM`） |
| `legacy/skeleton.md` | 语法示意 |
| `legacy/first_prompt.tpl.txt` `legacy/replan_prompt.tpl.txt` | 修 bug 第 1 版 / 重新规划的 user |
| `legacy/task_first_prompt.tpl.txt` `legacy/task_replan_prompt.tpl.txt` | 任务路径第 1 版 / 重新规划的 user |
| `legacy/replan_err.tpl.txt` | 重新规划里「上一版的报错」那一段（没有报错时整段不出现），占位 `{prev_err}` |
| `legacy/template_note.txt` | 第 1 版是模板的说明（`{note}`） |
| `legacy/lib_system.tpl.txt` | 定位.zs / 读改测.zs 共用的固定 system，占位 `{LOC_TAG}` `{RCT_TAG}` `{LOC_TAIL}` `{RCT_TAIL}` |

### 共用的小件（`prompts.py`、`v2.py`）
| 文件 | 内容 |
|---|---|
| `fix_prompt.tpl.txt` | 计划没过检查时让模型改脚本，占位 `{problem}` `{numbered}`（带行号的原脚本）；v2 的 plan_fix 也用 |
| `see.txt` | 各 user 里的「见系统提示」一句（占位 `{SEE}`） |
| `toolsub_system.txt` | 工具子任务（`toolsub.py`，dsl_options.subtask=tool）的 system |

旧路径模板占位的值：`intro`（项目说明一句）、`desc` `test` `test0` `files` `prev_script` `prev_out` `test_now` `diff`、`plan_cap` `budget` `versions_left`、
`ver` `next_ver`、`note`（带结尾空行的说明，没有就是空串）、`err`、`SEE`。拼哪几段、没内容时的默认文字（「（没有输出）」「（还没有改动源码）」）在 `legacy/prompts.py` 里。

### 资料包 code（`packs/code.py`）
- `packs/code/plan_rules.md`：规划规则里 code 专属的几条（`PLAN_RULES`，规划 system 第 5 项，在 `rules_head.md` 之后）。
- `packs/code/plan_rules_end.md`：同上，在 `rules_stop.md` 之后（`PLAN_RULES_END`）。

### 验收 code（`verify/code.py`）
- `verify/code/fix_sys.txt`：补改 system（`FIX_SYS`）。
- `verify/code/bound_sys.md`：边界复核写用例的 system（`BOUND_SYS`）。
- `verify/code/bfix_sys.txt`：边界补改 system（`BFIX_SYS`）。

补改 / 边界的 user 由代码按当次数据拼（`verify/code.py` 的 `_fix_user`、`boundary`），不在这里。
