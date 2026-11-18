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
| `project_workflow.wf` | 从一句需求做出多模块项目：架构设计 → 架构审查 → 按模块依次（分配 → 实现 → 模块验收，不过就模块内返工；接口在架构里一次约定好，实现和约定不一致就返工）→ 集成测试（场景写成测试）→ 集成验收 | `run_project.zs` |

`project_workflow.wf` 用到块内跳转（标记写在遍历里，每个模块各自返工）和 `清空`（每个模块重新收集实现记录），
格式见 `formats/architecture.json`、`formats/module_acceptance.json`，架构师的写法在 `agents/ARCHITECT/skills/architecture.md`。
离线测试：`tests/tools/test_wf_project.py`。
