# flows.py 的三处改动

## 一、_run 里创建引擎时挂上动词表

把原来的：

        c = _client(real)
        engine = DSLEngine(c, workdir=workspace, verbose=False)

改成：

        c = _client(real)
        engine = DSLEngine(
            c, workdir=workspace, verbose=False, verbs=_verbs()
        )


## 二、新增 _verbs()，放在 _run 前面

    _verb_cache = {}

    def _verbs():
        """动词表：扫描 workspace/verbs/，加上内置的 Python 动词。"""
        if "reg" not in _verb_cache:
            from tools import make_verbs
            reg = make_verbs(workspace / "verbs")
            register_python_verbs(reg, workspace)      # 见 verbs_py.py
            _verb_cache["reg"] = reg
        return _verb_cache["reg"]

注意：动词表缓存在闭包里，改了 verbs/ 下的脚本要重启才生效。
想热更新的话把 if 那行去掉，每次重新扫描（代价是每次调用都读一遍目录）。


## 三、新增一个列动词的工具，放在 check_flow 后面

    @reg.tool(
        "列出所有可用的动词及其参数。动词是流程脚本里能直接用的语句。",
        max_result=1000,
    )
    def list_verbs() -> str:
        v = _verbs()
        out = v.describe()
        if v.warnings:
            out += "\n\n[加载警告]\n" + "\n".join("  " + w for w in v.warnings)
        return out
