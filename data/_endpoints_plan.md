# 端点导出：让 .zs 成为接口地址的唯一出处

## 问题

`app2/build.py` 里有个手写的 `ENDPOINTS` 字典，把 `.ui` 的动作名映射到
后端路径。`routes/*.zs` 里也定义着接口。两边各写一遍，改一边另一边不知道。

## 为什么不能全自动推导

动作名和路径没有可靠的对应关系：`send` 对应的是 `/chat`，`submit` 对应
`/drill/answer`。靠「动作名等于路径最后一段」这种约定推的话，现有的路由
全要改名，而路径是给人看的 URL，不该迁就界面里的变量名。

所以要在 `.zs` 里显式说明这个接口服务于哪个动作。

## 一、接口行加「动作」

```
接口 POST /chat 动作 send
接口 POST /drill/answer 动作 submit
```

`tools/dsl_http.py` 的正则改成：

```python
# 接口 POST /chat 动作 send  ——  方法和动作都可省
API_RE = re.compile(
    r"^接口\s+(?:(GET|POST|PUT|DELETE)\s+)?(/\S*)"
    r"(?:\s+动作\s+(\S+))?\s*$", re.I)
```

`Endpoint.__init__` 收一个 `action` 参数存起来，`split_endpoints` 里：

```python
        out.append(Endpoint(m.group(1) or "POST", m.group(2), body,
                            src, i + 1, action=m.group(3) or ""))
```

## 二、导出函数

`dsl_http.py` 末尾加：

```python
def endpoints_of(routes_dir) -> dict:
    """扫路由目录，返回 {动作名: 路径}。

    只收声明了「动作」的接口——没声明的是纯后端接口（给别的程序调的），
    界面不需要知道它们。

    同一个动作名被两个接口声明时报错而不是取一个：那种情况下界面到底
    发到哪儿完全看扫描顺序，静默选一个会让人调半天。
    """
    table, _, _ = scan_routes(Path(routes_dir))
    out = {}
    for (method, path), ep in sorted(table.items()):
        if not ep.action:
            continue
        if ep.action in out:
            raise DSLError(
                f"动作「{ep.action}」被两个接口声明：{out[ep.action]} "
                f"和 {path}（{ep.src.name}:{ep.line}）")
        out[ep.action] = path
    return out
```

## 三、build.py 读它

`ENDPOINTS` 那个字典不删，降级成**兜底**——因为 `/chat` 和 `/reset`
现在还在 `app2/serve.py` 里，不在 `routes/` 下。全删的话 build 会报
missing_endpoint。

```python
# 动作名 -> 后端路径。
#
# 优先从 routes/*.zs 里读——那边的「接口 POST /x 动作 send」是唯一
# 出处，加个接口前端自动知道。
#
# 下面这份是兜底：/chat 和 /reset 还在 app2/serve.py 里实现，没搬进
# routes/。搬完之后这个字典就能删了。
FALLBACK_ENDPOINTS = {
    "send": "/chat",
    "reset": "/reset",
    "submit": "/drill/answer",
    "next": "/drill/next",
    "stop": "/drill/stop",
}


def load_endpoints() -> dict:
    """先拿 routes/ 里声明的，缺的用兜底补上。

    打印每个动作的来源，因为「界面发到哪个地址」是调试时第一个要确认
    的事——两处来源混在一起时更该说清楚。
    """
    declared = {}
    routes = ROOT / "routes"
    if routes.is_dir():
        try:
            from tools.dsl_http import endpoints_of
            declared = endpoints_of(routes)
        except Exception as e:
            print(f"  [提示] 读 routes/ 失败，全部用兜底：{e}")

    out = dict(FALLBACK_ENDPOINTS)
    out.update(declared)

    for action, path in sorted(out.items()):
        来源 = "routes" if action in declared else "兜底"
        print(f"  {action:8} → {path:20} [{来源}]")
    return out
```

`main()` 里：

```python
    print("读端点表：")
    endpoints = load_endpoints()
```

然后 `build_main` 用它而不是常量。

## 四、routes/drill.zs 加动作名

```
接口 POST /drill/answer 动作 submit
接口 POST /drill/next 动作 next
接口 POST /drill/stop 动作 stop
```

`/drill/start` 不加——界面上没有对应的动作，它是练习模式启动时由
`切到` 触发的，走的不是动作路径。

## 剩下的一步

`/chat` 和 `/reset` 搬进 `routes/`，`FALLBACK_ENDPOINTS` 就能删。

那要先解决一件事：对话模式要调 agent，而 DSL 现在没有调 agent 的能力。
所以这一步卡在别处，不是端点表的问题。
