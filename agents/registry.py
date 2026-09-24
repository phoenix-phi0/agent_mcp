"""工具注册表：把 Python 函数变成模型能调用的工具。

用法：

    reg = Registry()

    @reg.tool("读取文件内容")
    def read_file(path: str) -> str:
        ...

    reg.schemas()          # 传给智谱的 tools 参数
    reg.call("read_file", {"path": "a.txt"})

结果截断：
    工具返回的内容会进入对话历史，之后每一次请求都要重发一遍，
    所以长结果的成本是累积的。每个工具有一个 max_result 上限，
    超出部分截断并附提示，让模型知道内容不全、可以换个方式再取。
"""

import inspect
import json
from typing import Any, Callable

# Python 类型 -> JSON Schema 类型
_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# 工具结果的默认字符上限
DEFAULT_MAX_RESULT = 2000


def truncate(text: str, limit: int, hint: str = "") -> str:
    """超长就截断，并明确告诉模型内容不完整。"""
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    tail = f"\n\n[内容已截断：共 {len(text)} 字，只显示前 {limit} 字"
    tail += f"。{hint}]" if hint else "。]"
    return cut + tail


class Registry:
    def __init__(self, max_result: int = DEFAULT_MAX_RESULT):
        self._fns: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}
        self._limits: dict[str, int] = {}
        self._hints: dict[str, str] = {}
        self.default_max_result = max_result

    def tool(
        self,
        description: str,
        max_result: int | None = None,
        truncate_hint: str = "",
        **param_docs,
    ):
        """装饰器：注册一个工具。

        description   给模型看的功能说明
        max_result    该工具返回结果的字符上限，0 表示不限
        truncate_hint 截断时附给模型的提示，例如「用 start_line 分段读取」
        param_docs    「参数名=说明」形式补充每个参数的用途
        """
        def deco(fn: Callable) -> Callable:
            sig = inspect.signature(fn)
            props, required = {}, []

            for name, p in sig.parameters.items():
                ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
                item = {"type": _TYPES.get(ann, "string")}
                if name in param_docs:
                    item["description"] = param_docs[name]
                props[name] = item
                if p.default is inspect.Parameter.empty:
                    required.append(name)

            self._fns[fn.__name__] = fn
            self._limits[fn.__name__] = (
                self.default_max_result if max_result is None else max_result
            )
            self._hints[fn.__name__] = truncate_hint
            self._schemas[fn.__name__] = {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            }
            return fn
        return deco

    # ------------------------------------------------------------------

    def schemas(self, only: list[str] | None = None) -> list[dict]:
        """返回工具描述列表，only 可以限定子集。"""
        if only is None:
            return list(self._schemas.values())
        return [self._schemas[n] for n in only if n in self._schemas]

    def names(self) -> list[str]:
        return list(self._fns)

    def limit_of(self, name: str) -> int:
        return self._limits.get(name, self.default_max_result)

    def call(self, name: str, arguments: str | dict) -> str:
        """执行一个工具，返回字符串结果（异常也转成字符串）。"""
        if name not in self._fns:
            return f"错误：没有名为 {name} 的工具"

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError as e:
                return f"错误：参数不是合法 JSON（{e}）"

        try:
            result = self._fns[name](**arguments)
        except TypeError as e:
            return f"错误：参数不匹配（{e}）"
        except Exception as e:
            return f"错误：{type(e).__name__}: {e}"

        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False)

        return truncate(result, self._limits.get(name, self.default_max_result),
                        self._hints.get(name, ""))

    def merge(self, other: "Registry") -> "Registry":
        """把另一个注册表的工具并进来。"""
        self._fns.update(other._fns)
        self._schemas.update(other._schemas)
        self._limits.update(other._limits)
        self._hints.update(other._hints)
        return self


def describe(reg: Registry) -> str:
    """人类可读的工具清单，调试用。"""
    lines = []
    for name, s in reg._schemas.items():
        fn = s["function"]
        params = ", ".join(fn["parameters"]["properties"])
        lines.append(f"  {name}({params}) — {fn['description']}")
    return "\n".join(lines) or "  (无工具)"
