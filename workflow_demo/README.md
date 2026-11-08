# 多 agent 编排示例

`workflow.wf` 是讨论中的完整缩进式 DSL；`run.zs` 是普通 DSL 入口。
本目录的 `agents/` 下有四个角色：`ARCHITECT`、`ARCHITECT_GLM`、`ENGINEER`、`QA_ENGINEER`。每个角色都包含 `SOUL.md`、`agent.json` 和技能文件。

在 `workflow_demo` 作为工作目录时，执行 `run.zs` 会由 `编排执行`读取 `workflow.wf`。`任务分配`要求把每项的 `agent` 设为已配置的 `ENGINEER`。若要用其他 agent 名称，先建立同名文件夹。

这些示例配置的 `tools` 为空，工程师和 QA 只生成 JSON 记录，不会修改文件或实际运行测试。测试 `python -m tests.tools.test_workflow_demo` 使用假客户端，不发真实模型请求。
