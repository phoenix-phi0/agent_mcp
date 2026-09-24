# test_dsl.py 里 UI 测试的修法

`test_ui_parse` 第 379 行崩了，把它后面的 `test_ui_validate` 和
`test_ui_compile` 全挡住了——那两个至今没跑过。

## 病因

```python
check("动作吃到到端点", a.to, "/chat")
```

`Node` 上没有 `to` 字段。这是照旧设计写的：那时「远程」后面直接跟端点
地址，存进 `Node.to`。

现在的设计变了——「远程」只是 `FLAG_MODIFIERS` 里的一个旗标，存进
`modifiers` 列表，用 `has('远程')` 判断。**端点地址不在 Node 上**，
它按动作的 `name` 到外部传入的 endpoints 表里查（`validate` 的
`_check_endpoints`）。

这个改动是对的：端点是部署细节，`.ui` 描述界面意图，不该把 `/chat`
这种路径写死在里面。测试没跟上而已。

## 改法

把那一行换成：

```python
    check("动作标了远程", a.has("远程"), True)
```

如果原来那段还检查了端点内容，一并去掉——`.ui` 里现在没有端点信息可查。

## 顺带确认另外两个测试

`test_ui_validate` 和 `test_ui_compile` 从来没跑过，很可能也用了过时的
属性名。它们引用的东西：

```python
from .ui import parse, validate      # 397 行
from .ui import compile_ui           # 409 行
```

这两个函数现在都还在（`ui.py` 的三阶段管线是 parse → bind → validate，
`compile_ui` 串起三步并分发后端），所以 import 不会挂。但里面 check 的
字段名要逐个对一下，尤其是：

| 旧名 | 现在 |
| --- | --- |
| `to` | 没有了，端点走外部 endpoints 表 |
| —— | `goto`（切到）、`opens`（打开） |
| —— | `submit_action`、`clears`、`modifiers` |

Node 现在有 20 个字段：kind、name、label、type、widget、bind、when、
hint、goto、opens、required、role、ratio、cols、size、clears、
submit_action、modifiers、children、line。

## 更该做的一件事

**把 UI 测试从 test_dsl.py 里搬出去**，单独一个 `test_ui.py`。

现在的问题不只是这一行写错——是 UI 那条线的测试跟 DSL 引擎的测试绑在
同一个文件里，`.ui` 语法一改就把 DSL 的测试报告一起弄崩。这次是最后
三个测试被挡住，如果 UI 测试排在中间，挡住的就是一半。

拆开之后：

```
py -m tools.test_dsl     引擎，93 项
py -m tools.test_ui      界面语言
```

`run_tests` 那个 MCP 工具可以两个都跑，分别报告。这样一边坏了另一边的
结果照样看得见。
