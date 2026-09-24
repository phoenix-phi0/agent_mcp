# 五处调用方的改法

统一到 `tools/packs.py` 之后，各处的 `_verbs()` / `_make_verbs()` 全删掉。

---

## 1. `agents/flows.py`

**删掉** `_verbs()` 函数、`_cache` 字典、`DEFAULT_PACKS` 常量、
`verbs_root` 的计算，以及 `make_flow_tools` 签名里的 `verbs_dir` 和
`packs` 两个参数。

`_run` 里创建引擎那段：

```python
        from tools.packs import engine_for

        c = _client(real)
        engine = engine_for(c, workspace, packs=DEFAULT_PACKS, verbose=False)
        engine.vars.update({k: str(v) for k, v in vars_.items()})
```

`packs=DEFAULT_PACKS` 是过渡用的——`讲解.zs` 和 `词汇扩展.zs` 没写
「用包」，靠预加载才有动词可用。等它们也声明了，这个参数去掉，
改成 `engine_for(c, workspace, verbose=False)`，那时脚本才真正自描述。

`_needed()` 里判断动词名用的 `_verbs()` 换成：

```python
    def _needed(script: str) -> list[str]:
        from tools.packs import registry
        v = registry(workspace=workspace)
        return [p for p in scan_params(script) if not v.has(p)]
```

`list_verbs` 工具换成：

```python
    @reg.tool("列出流程脚本里可以使用的动词及其参数，按包分组。", max_result=1000)
    def list_verbs() -> str:
        from tools.packs import describe
        return describe(workspace=workspace)
```

---

## 2. `agents/serve.py` 与 `app2/serve.py`

两份文件里各有一套 `_verbs()` 和 `call_verb()`，**整段删掉**，换成：

```python
from tools.packs import call_verb as _call_verb

def call_verb(name: str, *args) -> str:
    return _call_verb(name, *args, workspace=WORKSPACE)
```

`_reload()` 里补一句清缓存——否则重载了模块，动词表还是旧的：

```python
def _reload():
    for name in [n for n in list(sys.modules) if n.startswith(("agents", "tools"))]:
        del sys.modules[name]
    _agents.clear()
    from tools.packs import clear_cache
    clear_cache()
```

注意顺序：先删模块再 import，拿到的才是新的 `clear_cache`。

---

## 3. `fs.py`

**删掉** `_make_verbs()` 和 `PACKS` 常量。

`dsl_run` 改成：

```python
@mcp.tool
def dsl_run(key: str, script: str, real: bool = False) -> str:
    """执行 DSL 脚本。real=False 用假客户端，不消耗额度。"""
    check(key)
    from tools import MockClient
    from tools.packs import engine_for

    client = _client() if real else MockClient()
    # 不预加载：脚本自己写「用包」，顺便拿到严格模式
    engine = engine_for(client, DATA, verbose=False)
    out = engine.run(script)

    if engine.verbs and engine.verbs.warnings:
        out += "\n\n[动词加载警告]\n" + "\n".join(
            "  " + w for w in engine.verbs.warnings)
    if not real:
        calls = "\n".join(f"  {c['type']}: {c.get('prompt','')[:60]}"
                          for c in client.calls)
        out += f"\n\n--- 模拟调用 {len(client.calls)} 次 ---\n{calls}"
    return out
```

`list_verbs` 换成：

```python
@mcp.tool
def list_verbs(key: str) -> str:
    """列出所有已加载的动词，按包分组。"""
    check(key)
    from tools.packs import describe
    return describe(workspace=DATA)
```

---

## 4. `dsl/run.py`

`load_verbs()` 整个删掉，`run_script` 里换成：

```python
from tools.packs import engine_for, describe

def run_script(text, real, verbose, show_calls):
    WORK.mkdir(exist_ok=True)
    client = make_client(real)
    engine = engine_for(client, WORK, verbose=verbose)
    ...
```

但这个环境的包在 `dsl/verbs/` 而不是项目的 `verbs/`，所以要么把
`JP_DATA_DIR` 指过去，要么直接用 `DSLEngine(..., verbs_root=HERE/"verbs")`。

后者更直白——这个环境本来就该有自己的包目录：

```python
    engine = DSLEngine(client, workdir=WORK, verbose=verbose,
                       verbs_root=HERE / "verbs")
```

`--verbs` 那个分支改成读目录自己列，或者接受它只列已加载的（空的）。

`scripts/hello.zs` 开头加 `用包 common`。

---

## 5. `tools/__init__.py`

导出加上：

```python
from .packs import verbs_root, registry, engine_for, call_verb, describe
```

---

## 改完之后

「加载哪些包」只剩两个来源：脚本里的 `用包`，以及过渡期 `flows.py` 传的
`DEFAULT_PACKS`。加新包不用改任何 Python 代码。

`clear_cache()` 是新增的一环——之前四处 `_verbs()` 各自缓存在闭包里，
改了动词包必须重启服务器。现在缓存集中，热重载能清掉。
