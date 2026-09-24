# -*- coding: utf-8 -*-
"""本环境的客户端：默认假的，需要时才接真实模型。

假客户端不是「测试替身」这么简单——它决定了这个环境能不能随便试。
每跑一次脚本都真发请求的话，写语法的时候不敢反复跑，调试就变得束手束脚。

三种模式：

    EchoClient   默认。把提示词回显成 [回声] 开头的文本，不发请求。
                 好处是看得见变量插值后的实际内容——这正是调试时想看的。

    ScriptClient 按预设脚本依次返回，用来写确定性的测试。

    真实客户端   --real 时才加载，读主项目的 config.json。
"""

import sys
from pathlib import Path


class EchoClient:
    """把提示词原样回显。不发请求，不花钱，看得见插值结果。"""

    def __init__(self, model: str = "echo"):
        self.model = model
        self.default_temperature = 0.7
        self.embedding_model = "echo-embedding"
        self.image_model = "echo-image"
        self.calls: list[dict] = []

    def _log(self, kind: str, **kw) -> None:
        self.calls.append({"type": kind, **kw})

    def chat(self, prompt, system=None, temperature=None, **kw) -> str:
        self._log("chat", prompt=prompt, system=system, temperature=temperature)
        return f"[回声] {prompt}"

    def chat_messages(self, messages, temperature=None, **kw) -> str:
        last = next((m["content"] for m in reversed(messages)
                     if m.get("role") == "user"), "")
        self._log("chat_messages", prompt=last, turns=len(messages))
        return f"[回声#{len(messages)}] {last}"

    def chat_raw(self, messages, **kw) -> dict:
        return {"choices": [{"message": {
            "role": "assistant", "content": self.chat_messages(messages)}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    def stream(self, prompt, system=None, temperature=None, **kw):
        self._log("stream", prompt=prompt, system=system)
        for ch in f"[回声] {prompt}":
            yield ch

    def stream_messages(self, messages, temperature=None, **kw):
        for ch in self.chat_messages(messages):
            yield ch

    def embed(self, texts, model=None):
        items = texts if isinstance(texts, list) else [texts]
        self._log("embed", count=len(items))
        return [[0.0] * 8 for _ in items]

    def image(self, prompt, model=None):
        self._log("image", prompt=prompt)
        return "https://example.invalid/echo.png"


class ScriptClient(EchoClient):
    """按预设依次返回，用完之后重复最后一条。写测试用。

        c = ScriptClient(["第一次", "第二次"])
    """

    def __init__(self, replies: list[str]):
        super().__init__(model="script")
        self.replies = list(replies)
        self._i = 0

    def _next(self) -> str:
        if not self.replies:
            return ""
        r = self.replies[min(self._i, len(self.replies) - 1)]
        self._i += 1
        return r

    def chat(self, prompt, system=None, temperature=None, **kw) -> str:
        self._log("chat", prompt=prompt, system=system, temperature=temperature)
        return self._next()

    def chat_messages(self, messages, temperature=None, **kw) -> str:
        last = next((m["content"] for m in reversed(messages)
                     if m.get("role") == "user"), "")
        self._log("chat_messages", prompt=last, turns=len(messages))
        return self._next()

    def stream(self, prompt, system=None, temperature=None, **kw):
        self._log("stream", prompt=prompt, system=system)
        for ch in self._next():
            yield ch


def make_client(real: bool = False):
    """real=True 时才去加载真实客户端，否则连 config 都不读。"""
    if not real:
        return EchoClient()
    try:
        from tools import ZhipuClient
        return ZhipuClient()
    except Exception as e:
        print(f"接不上真实模型（{type(e).__name__}: {e}），改用回声客户端")
        return EchoClient()
