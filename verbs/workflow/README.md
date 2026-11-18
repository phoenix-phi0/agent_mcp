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

`标记` 可以写在任何一层（最外层、`如果`和`遍历`的子块里），名字全脚本唯一；`跳转`只能跳到同一层或外层的标记，跳进别的子块在开跑前就报错。跳转次数按「目标所在那一层」的每一轮分开算：标记写在`遍历`里时，每一项各自最多 N 次（如每个模块验收不过各自返工）；跳到`遍历`外面的标记会离开遍历，次数照旧全局算。

`文本`和`存储`可以写几项，拼成一个对象，只给下一步真正要用的部分：`文本 module built arch.stack arch.conventions` 得到 `{"module": …, "built": …, "arch.stack": …, "arch.conventions": …}`；`存储 built name=module.name interfaces=mcheck.interfaces_actual` 每次只存这两个字段。每项是引用（可带花括号）或`键=引用`，引用取不到值就报错；引用后面加 `[字段,字段]` 只留这几个字段，用在对象列表上就是每一项只留这几个字段，如 `modules=arch.modules[name,provides]`。只写一个引用时和原来一样存整个值。`清空 x` 把 x 设成空列表。

```
遍历 m 于 plan.modules
    标记:r
    实现
        任务 m.name
        角色 ENGINEER
        记录 impl
    验收
        任务 m.name
        角色 QA_ENGINEER
        文本 impl
        记录 check
    如果 check.decide == 需修改
        跳转 r 最大 2
```

`审查任务.zs` 是独立的单文件脚本动词，仍使用 `派任务`。它不通过这里的 agent 配置。任务块仅执行配置的模型和工具调用；配置里没有写文件工具时，`任务实现`与`代码修改`只会得到模型返回的记录，不会改项目文件。
