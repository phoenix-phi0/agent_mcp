# 多 agent 编排示例

`workflow.wf` 是讨论中的完整缩进式 DSL；`run.zs` 是普通 DSL 入口。
本目录的 `agents/` 下有四个角色：`ARCHITECT`、`ARCHITECT_GLM`、`ENGINEER`、`QA_ENGINEER`。每个角色都包含 `SOUL.md`、`agent.json` 和技能文件。

在 `workflow_demo` 作为工作目录时，执行 `run.zs` 会由 `编排执行`读取 `workflow.wf`。`任务分配`要求把每项的 `agent` 设为已配置的 `ENGINEER`。若要用其他 agent 名称，先建立同名文件夹。

这些示例配置的 `tools` 为空，工程师和 QA 只生成 JSON 记录，不会修改文件或实际运行测试。测试 `python -m tests.tools.test_workflow_demo` 使用假客户端，不发真实模型请求。

## 几条流程

| 流程 | 用途 | 入口示例 |
|---|---|---|
| `workflow.wf` / `cost_workflow.wf` | 从一句需求做一个模块：接口约定 → 审查 → 分配（按成本）→ 实现 → 验收 | `run_cost.zs`、`run_algo.zs` |
| `feature_workflow.wf` | 在已有项目上按写好的设计加功能（可以跨多个模块） | `run_confirm_p1.zs` |
| `refactor_workflow.wf` | 重构已有代码，行为不变 | `run_refactor.zs` |
| `meeting_workflow.wf` | AI 会议：参会角色按顺序轮流发言（可以有人：`HUMAN`），可点名追问，主持人每轮判断要不要再开一轮（最多三轮），最后出结论 | `run_meeting.zs` |
| `frontend_workflow.wf` | 给已有 JSON 接口的后端做前端：界面设计 → 设计评审会 → 按结论改设计 → 按页面实现和验收（jsdom 加载真实页面、请求打到真后端）→ 端到端测试 → 整体验收 | `run_frontend.zs` |
| `project_workflow.wf` | 从一句需求做出多模块项目：架构设计 → 架构审查 → 按模块依次（分配 → 实现 → 模块验收，不过就模块内返工；接口在架构里一次约定好，实现和约定不一致就返工）→ 集成测试（场景写成测试）→ 集成验收 | `run_project.zs` |

`project_workflow.wf` 用到块内跳转（标记写在遍历里，每个模块各自返工）和 `清空`（每个模块重新收集实现记录），
格式见 `formats/architecture.json`、`formats/module_acceptance.json`，架构师的写法在 `agents/ARCHITECT/skills/architecture.md`。
离线测试：`tests/tools/test_wf_project.py`。

**会议和人。** `meeting_workflow.wf` 的入口要设 `topic`、`background`（没有就写「无」）、`attendees`（逗号分隔，按发言顺序），
可选 `moderator`（默认 `MODERATOR`，写 `HUMAN` 就是人来判断和拍板）。全部发言在 `minutes`，结论在 `decision`
（格式 `formats/speech.json`、`meeting_check.json`、`meeting_decision.json`）。
`agents/HUMAN` 是人的卡：`agent.json` 里 `"model": "human"`。受控运行轮到人的卡就停下（不管模式和确认规则），
在查看器上按格式交结果；这一步不能「执行」，要让 AI 代答就换卡或给这个角色换模型。不受控的运行碰到人直接报错。
离线测试：`tests/tools/test_wf_meeting.py`。

**前端。** `frontend_workflow.wf` 全自动跑完，人在查看器上随时介入（暂停、确认规则、替某一步交结果、退回）；想在评审会上发言就把 `HUMAN` 加进 `review_attendees`。
入口要设 `content backend stack goal project web_dir test_cmd review_attendees`，可选 `designer moderator page_engineer page_qa`。
设计师（`DESIGNER`，只读）读后端代码写 `formats/frontend_design.json`：第一页固定是前端骨架（开发服务、测试脚本、共用部分），
每页写调的接口（照后端代码）、元素、操作、状态、验收和测试，另有端到端场景 `flows`。评审会就是会议流程的写法（发言、追问、主持判断、结论），
结论有 `todo` 才改设计。页面由 `FRONTEND_ENGINEER` 实现、`FRONTEND_QA` 验收，工程师报告设计和后端对不上时先交设计师裁决（`design_notes`）。
两张卡放行的测试命令是 `./web/run_tests.sh`，`web_dir` 换名字要一起改卡。截图和看图检查还没接（要装浏览器）。
离线测试：`tests/tools/test_wf_frontend.py`。

**会议页和会后交给流程。** 查看器地址后面加 `meeting/` 就是会议页（`tools/meeting_web`，源码和测试在 `work/meeting_room`，
是用前端流程做出来的）：开会（入口 `meeting.zs`，议题、参会名单、主持人启动时用 vars 传）、会议列表、会议室（轮到 `HUMAN` 时出表单）。
会开完以后会议室里有「交给流程」：选一个声明了 `content`（重构是 `goal`）的入口，结论自动拼成需求填进去，改过再启动。
`run_project.zs`、`run_frontend.zs`、`run_refactor.zs` 开头用 `# 参数：content? project?` 声明了可传参数，
脚本里写成 `设 content = {content 或 原来的默认值}`：不传和以前一样。别的入口想接会议结论，照这个写法加声明就行。
