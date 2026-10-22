# 改文件 新定位方式（feat/edit-locate）实验报告

日期：2026-10-22（JST）。分支 `feat/edit-locate`（基于 master 6ccf13b），未推送、未合并。

## 改了什么

1. **点名函数整段替换**：`#改法` 段里写 `@@ 改 路径 函数 名`，块里只写整个新函数（没有 `=======`），不用抄原文。
   JSON 形式是 `{file, func, new}`（别名：`函数` / `function` / `fn`）。
   - .zs：从 `[公开 ]函数 名` 到同缩进的 `结束`。
   - .py：从 def/class 头到缩进回落，支持 `Class.method`。
   - 函数名必须唯一。找不到时列出候选，有多个时报行号。新函数首行缩进不对就整体挪齐。
2. **函数内锚点**：`@@ 改 路径 函数 名` 下写 原文 / `=======` / 新文，只在这个函数的范围里找原文，原文在函数内唯一即可。
3. **缩进容错**：精确匹配 0 次时，逐行比较并忽略行首、行尾空白。只有恰好一处匹配、且各行缩进差一致时才套用，新文按同样的缩进差挪，msg 里会注明。
4. `改文件` 和 `核对计划`（计划检查）共用同一个 `_resolve`，检查结果和实际套用一致。`核对计划` 新增可选参数 `info`，记录每处用了哪种非精确定位。
5. `dsl_sections`：
   - 解析、回写 `函数 名`，`edits_text` 能往返。
   - 第二个提交 0777dd3：块结尾后紧跟着重复出现的一行 `>>>>>>> 新文` 会被忽略，其余情况照旧报错。
6. 提示词：
   - cheat.md、shared/verbs.md、tips_plan.md
   - dslproj 的 verbs.md、notes.md 和 PLAN_SYSTEM 输出要求
   - dslmcp 的 DESC
   - plan_fix.md 用户模板（原文找不到或不唯一时改用函数写法或锚点）
7. 旧写法的行为不变，唯一的放宽是"精确 0 次 → 尝试缩进容错"。已有测试全部通过。

## 测试

- 新增 `tests/tools/test_dslagent_edit_locate.py`：61 项。
- `tests/tools/test_dslagent*.py` 和 `tests/dsl/test_edit_budget.py` 全部通过，0 失败。
  - 和 master 基线一致，比如 edits 60、models 198、roles 74、split 55、v2 76、v3 417。
  - 唯一差别是多了新文件的 61 项。

## 实验：T1 q5（真实 v2 规划 + 只读 dsl MCP，模块 report）

- 脚本：`/workspace/dslagent_exp/edit_locate/el.py`，用 worktree 的代码。项目是 goose_t1/proj 的拷贝。
- user 提示词沿用原来抓下来的 `01_plan.prompt.txt`。system 用新提示词重新生成（`v2.plan_system(dslproj)`）。
  - 已核对：master 生成的 system 和原来抓下来的一字不差，所以 system 的差别只来自这次改的提示词。
- 判定：`v2.check`，包括白名单、`#改法` 核对和空跑。

### iso 和非 iso 的区别

- goose 会自动扫描 `~/.claude/skills` 并公布 `load_skill` 工具。这台机器上有一个同步来的 `agent-mcp` skill，名字和仓库很像。
- 高强度下，luna 每次（3/3）都先调用 `load_skill("agent-mcp…")`。引擎发现非 dsl 的工具调用就直接杀掉（"尝试调用工具"），所以没有任何输出。
- **iso** 是指只在实验进程里把 `HOME` 指向一个空目录（/tmp/elocate/gh），同时把 `XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`XDG_STATE_HOME`、`XDG_CACHE_HOME` 指回真实目录。
  - 这样 goose 的配置和登录不变，但看不到 `~/.claude/skills`，只剩内置的 goose-doc-guide 和 web-search。
  - 没有改任何文件。
- iso 组还设了 `DSLAGENT_GOOSE_FIRST_CAP=400`，因为高强度下首字较慢。
- **非 iso** 就是正常的 HOME。

### 结果（每组 3 次）

| 组 | 通过 | 每次结果 / 失败原因 | 定位方式使用 |
|---|---|---|---|
| goose 默认强度（非 iso） | 0/3 | 0：把 `#改法` 写在脚本前面，后面的语句（`设 res = 改文件 {e1}` 等）被吞进 `#改法` 段，`#改法 e1` 还重复写了两份；1：old 忽略缩进后出现 2 次、另有一处找不到；2：old 出现 2 次（`设 acc = 调用 account.学生列表`），整份计划只差这一处 | 锚点 4（只在第 0 次），函数 0，容错 0 |
| goose 高强度（非 iso） | 0/3 | 3 次都因调用 load_skill 被杀，没有输出 | — |
| **goose 高强度 iso** | **3/3** | 全部通过，每次 215–283 秒 | 锚点 28，其中 2 处是锚点+缩进容错；函数 0 |
| goose 默认强度 iso | 2/3 | 0：同样是 `#改法` 写在前面、语句被吞；1、2 通过 | 锚点 12，函数 0 |
| sonnet | 3/3 | 全部通过，每次 26–31 秒 | 锚点 9，函数整段 1，容错 0 |

旧结果（T1，旧代码 + 旧提示词）：goose 0/3，sonnet 3/3。

### 补充分析

- **旧计划用新检查重判（不调模型）**：旧 goose 计划仍然是 0/3。
  - 缩进容错把 q5_goose_1 的问题从 4 个减到 2 个，但剩下的是"不唯一"，单靠容错解决不了。
- **反事实**：把 goose 高强度 iso 计划里的锚点去掉，每份都会多出 1 处"old 出现 2 次"（`设 ords = 查询表 …` 那段），sonnet_1 也一样。
  - 也就是说，这几份能通过，靠的正是锚点。
- **模式使用**：
  - goose 一旦用新写法，几乎全用锚点，没用过整函数替换。sonnet 用了 1 次整函数替换。
  - 缩进容错一共触发 2 次，都是在锚点内部。
- **重复的 `>>>>>>> 新文`**：第一批 goose 默认强度 3/3 都在末尾多写了一行。0777dd3 之后忽略这一行，三份结果已重判，仍然失败，原因是上表里的其它问题。

### 负载重试

- 实验期间，OpenAI 端频繁返回 `server_is_overloaded`。第一批 goose 6 次全是这个原因导致无输出，结果放在 `res_try1/`，没有算进表里。
- 后来 harness 改成无输出（且不是因为调用工具被杀）时最多重试 8 次，每次间隔 30 秒。tries 字段记录在 `res/*.json`。
- 也碰到过 `Stream decode error` 和首字前静默超时，重试后都正常了。

## 强度有没有传给 goose

- master 的 `call_goose` 已经把强度通过环境变量 `CHATGPT_CODEX_REASONING_EFFORT` 传下去了（`goose:gpt-6-luna:high` → high）。
  - goose 1.55 的二进制里有 `get_chatgpt_codex_reasoning_effort` 和 `Invalid CHATGPT_CODEX_REASONING_EFFORT` 的报错文本，说明 chatgpt_codex provider 读的就是这个变量。
- `GOOSE_THINKING_EFFORT` 是 goose 的通用设置，对 chatgpt_codex 是否有效没有确认，所以引擎不需要改，这个分支也没改 engines.py。
- 小样本测速：同一道题 codex_high 约 19 秒、2326 输出 token，不设约 9 秒、约 920 token，说明强度确实生效。
  - 给一个非法值（bogus）不会报错，说明它可能被静默忽略。
- 高强度下的行为差异也很明显：会去调 load_skill，计划更规整，3/3 通过。

## 结论和建议

- 建议合并。
  - 旧写法完全兼容，测试全部通过。
  - goose 规划从 0/3 提升到 iso 下默认强度 2/3、高强度 3/3。
  - sonnet 保持 3/3，而且也主动用了新写法。
- 合并时或合并后建议另外处理两件事：
  1. 让 goose 引擎看不到用户的 `~/.claude/skills`，比如照 iso 的做法隔离 HOME；或者在 mcp 模式下放行 load_skill。否则高强度会 3/3 被杀。
  2. goose 剩下的主要失败是把 `#改法` 写在脚本前面，导致后面的语句被吞。可以在 autoclose 或 strip_prose 里加一个修复：把 `#改法` 段后面的语句挪回主脚本。
- 成本：sonnet $0.32（0.2297 + 0.0494 + 0.0408）。goose 走工作账号订阅，不计费（goose 估算每次约 $0.003）。

## 追加：失败的 goose 计划交回 plan_fix 能救回几份（2026-10-22 16:18–17:05 JST，未跑完）

- 脚本：`/workspace/dslagent_exp/edit_locate/fixrun.py`，结果逐条写在 `fix/<组>_<case>.json`。
- 按真实 v2 路径走，用的是 feat/edit-locate 的代码：strip_prose / autoclose → `v2.check` → plan_autofix → `prompts.fix_prompt`（plan_fix 模板）→ goose（system = `plan_system(dslproj, "goose")`，挂只读 dsl MCP）。
- 用 iso 模式，每个 case 最多 3 轮。无输出（overloaded）不算一轮，最多重试 25 次，每次间隔 45 秒。
- 第一版脚本把无输出也算成一轮，那批结果放在 `fix/discard/`，只作为补充数据。
- 四个 case 是 goose_0、goose_1、goose_2、goose_iso_0。分两组：def（默认强度，跟原 run 一致）和 high（高强度对照）。

| case | 原失败原因 | def | high |
|---|---|---|---|
| goose_0 | `#改法` 写在脚本前面，后面的语句被吞进段里 | 第 1 轮通过 | 第 1 轮通过 |
| goose_1 | old 不唯一 + old 以「结束」开头找不到 | r1 仍失败（第 7 处 old 在函数 学生详情 内找不到，开头「结束」）；r2 因 overloaded 重试 25 次仍无输出；r3 未跑完。discard 那批的 r2 也是同一个错误 | r1 同样的错误（discard 那批，r2/r3 无输出） |
| goose_2 | old 出现 2 次（`设 acc = 调用 account.学生列表`） | 未跑到 | 未跑到 |
| goose_iso_0 | 同 goose_0（`#改法` 写在前面） | 未跑到 | 未跑到 |

- plan_autofix 在这几份上都没修到东西（autofix=0）。

### 阻塞情况

- 约 16:35 起，OpenAI 端持续返回 `server_is_overloaded`，连「只回数字 7」这样的小请求也 3/3 失败。
- 另外，机器在等待期间会休眠，后台任务也跟着停。
- 任务还挂在后台，会按 def → high 的顺序继续跑。def_goose_1.json 是部分结果，脚本跳过已存在的 json，要重跑就先删掉它。

### 目前的结论

- 能救的：结构类错误（`#改法` 位置不对）一轮就能修好，2/2。
- 救不了的：内容类错误（goose_1 的 old「结束」）连续 2–3 次给同样的反馈，goose 照样犯同样的错，多给几轮也没用。
- 建议：goose 的 plan_fix 保持 1 轮（现在的默认值），最多 2 轮。与其加轮数，不如改反馈文字（比如给出函数里实际的结尾几行），或者加程序修复（把被吞的语句挪回主脚本）。
- 轮数在 `tools/dslagent/agents.py` 第 108 行 `PLAN = _agent("plan.md", …, rewrites=1)`，v2 用 `for k in range(1 + AG.PLAN.rewrites)` 读它（v2.py 约 647 行）。plan.md 前言里的「重写 1 次」只是说明文字。
