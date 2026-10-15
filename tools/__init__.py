# 包入口不一次性导入子模块：python -m tools.cbatch 这类入口只为跑一个模块，
# 以前每次起进程都连带导入 zhipu→requests、dsl、config 等，约 0.45 秒。
# 下面这些名字照旧能 `from tools import X` / `tools.X`，第一次用到时才导入。
import importlib

_LAZY = {
    "ZhipuClient": "zhipu",
    "MockClient": "mock",
    "VerbRegistry": "verbs",
    "VerbError": "verbs",
    "parse_param_decl": "verbs",
    "DSLEngine": "dsl",
    "DSLError": "dsl",
    "run_script": "dsl",
    "make_verbs": "dsl",
    "RESERVED": "dsl",
    "ColabVllm": "colab_vllm",
    "ColabVllmError": "colab_vllm",
}

__all__ = [
    "config",
    "ZhipuClient",
    "MockClient",
    "VerbRegistry",
    "VerbError",
    "parse_param_decl",
    "DSLEngine",
    "DSLError",
    "run_script",
    "make_verbs",
    "RESERVED",
    "ColabVllm",
    "ColabVllmError",
]


# 以前包入口顺带导入了这些子模块，`import tools` 之后直接 tools.zhipu 也能用；
# 照旧支持，用到时再导入。
_SUBMODULES = {"config", "zhipu", "mock", "verbs", "dsl", "dsl_core", "dsl_calc",
               "dsl_history", "dsl_model", "llm_router"}


def __getattr__(name):
    if name in _LAZY:
        value = getattr(importlib.import_module(f".{_LAZY[name]}", __name__), name)
    elif name in _SUBMODULES:
        value = importlib.import_module(f".{name}", __name__)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
