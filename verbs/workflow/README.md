# workflow 动词包

原版 DSL 引擎无需修改。普通 DSL 加载本包，再执行工作目录内的缩进式编排脚本：

```text
用包 workflow
设 content = 设计用户接口
编排执行 flow.wf
```

每个 agent 放在工作目录的 `agents/<角色名>/`：

```text
agents/ARCHITECT/
  SOUL.md           角色的系统指令
  agent.json        模型、思考强度、可用工具和技能
  skills/           可选；技能文件由配置点名
```

`agent.json` 示例：

```json
{
  "model": "cli:claude/sonnet",
  "effort": "high",
  "tools": ["相加"],
  "packages": ["common"],
  "skills": ["skills/review.md"],
  "max_tool_rounds": 3
}
```

工作目录的 `agents/` 优先；若没有该角色，才查公共的 `tools/dslagent/agent_profiles/`。
`model` 用现有 DSL 模型路由名称。`effort` 目前只支持 `cli:claude/…`，会传成 `@high` 等模型后缀；其他模型写 `effort` 会在加载时报错。
`tools` 是模型实际可调用的 DSL 动词白名单；`packages` 先加载动词包，工具名必须存在。`skills` 是角色目录内的 Markdown 文件，其内容附在 `SOUL.md` 后面进入系统提示词。不存在或越出角色目录的技能会报错。工具调用最多按 `max_tool_rounds` 轮运行。

编排脚本里任务块可写 `任务`、`角色`、`文本`、`记录`；`任务` 可省略，此时用块名。模型必须返回 JSON 对象。`如果`、`遍历`、`存储`、`标记`和`跳转 … 最大 N`由包内解释器执行；超过跳转次数时报错。示例见 `examples/flow.wf`，角色目录见 `examples/agents/`。

`审查任务.zs` 是独立的单文件脚本动词，仍使用 `派任务`。它不通过这里的 agent 配置。任务块仅执行配置的模型和工具调用；配置里没有写文件工具时，`任务实现`与`代码修改`只会得到模型返回的记录，不会改项目文件。
