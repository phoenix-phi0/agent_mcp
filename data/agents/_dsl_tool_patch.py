def make_dsl_tool(
    workspace: Path,
    client=None,
    max_calls: int = 20,
    real: bool = True,
) -> Registry:
    """把 DSL 引擎包成工具，让 agent 能跑批量任务。

    client  传 agent 自己的客户端，DSL 里的「问」就会走真实模型；
            传 None 且 real=True 时懒加载 ZhipuClient。
    real=False 用 MockClient，只验证脚本结构，不消耗额度。
    max_calls 限制单次脚本能发起的模型调用次数，防止循环失控。
    """
    reg = Registry()
    workspace = Path(workspace).resolve()

    def _engine():
        from tools import DSLEngine, MockClient
        if real:
            c = client
            if c is None:
                from tools import ZhipuClient
                c = ZhipuClient()
        else:
            c = MockClient()
        return DSLEngine(c, workdir=workspace, verbose=False), c

    @reg.tool(
        "执行一段 DSL 脚本，适合批量任务（对多个对象重复同样的处理）。"
        "脚本里的「问」会真实调用模型，注意成本。语法先调 dsl_help 查看。",
        script="DSL 脚本内容，每行一条语句",
    )
    def run_dsl(script: str) -> str:
        from tools import DSLError

        engine, c = _engine()

        # 粗略估算：数一下会触发模型调用的语句
        heavy = sum(
            1
            for ln in script.splitlines()
            if ln.strip().startswith(("问", "流式", "对话", "ask", "stream", "chat"))
        )
        if heavy > max_calls:
            return (
                f"[已拒绝] 脚本包含约 {heavy} 处模型调用，"
                f"超过上限 {max_calls}。请拆分或减少循环规模。"
            )

        try:
            out = engine.run(script)
        except DSLError as e:
            return f"[脚本错误] {e}"
        except Exception as e:
            return f"[执行失败] {type(e).__name__}: {e}"

        used = len(getattr(c, "calls", []))
        suffix = f"\n[本次模型调用 {used} 次]" if used else ""
        return (out or "(无输出)") + suffix

    @reg.tool(
        "先用假客户端试跑 DSL 脚本，只验证语法和变量插值，不消耗额度。"
        "写完脚本建议先用这个检查一遍。",
        script="DSL 脚本内容",
    )
    def check_dsl(script: str) -> str:
        from tools import DSLEngine, MockClient, DSLError

        mock = MockClient()
        engine = DSLEngine(mock, workdir=workspace, verbose=False)
        try:
            out = engine.run(script)
        except DSLError as e:
            return f"[脚本错误] {e}"
        except Exception as e:
            return f"[执行失败] {type(e).__name__}: {e}"

        lines = [f"  {c['type']}: {c.get('prompt', '')[:70]}" for c in mock.calls]
        return (
            f"语法正确。输出预览：\n{out or '(无输出)'}\n\n"
            f"将会发起 {len(mock.calls)} 次模型调用：\n" + "\n".join(lines)
        )

    @reg.tool("返回 DSL 的语法说明，写脚本前先看这个。")
    def dsl_help() -> str:
        from tools import dsl
        return dsl.__doc__ or "无说明"

    return reg
