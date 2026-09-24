"""本地测试用的假客户端，接口与 ZhipuClient 一致，但不发网络请求。

用法：

    from tools import DSLEngine, MockClient

    mock = MockClient()
    engine = DSLEngine(mock, verbose=False)
    out = engine.run("问 甲 = 你好\\n打印 {甲}")

    print(out)            # 看输出
    print(mock.calls)     # 看发生了哪些调用

指定回复内容：

    # 按顺序返回
    MockClient(replies=["第一次", "第二次"])

    # 按关键词匹配
    MockClient(rules={"介绍": "这是介绍", "诗": "两行诗"})

    # 自定义函数
    MockClient(handler=lambda prompt, system: prompt[::-1])
"""


class MockClient:
    """假的智谱客户端，用于离线测试 DSL 脚本。"""

    def __init__(self, replies=None, rules=None, handler=None,
                 model="mock-model"):
        self.model = model
        self.default_temperature = 0.7
        self.embedding_model = "mock-embedding"
        self.image_model = "mock-image"

        self.replies = list(replies) if replies else []
        self.rules = rules or {}
        self.handler = handler

        self.calls: list[dict] = []      # 每次调用的完整记录
        self._reply_index = 0

    # ------------------------------------------------------------------

    def _make_reply(self, prompt: str, system: str | None) -> str:
        if self.handler:
            return self.handler(prompt, system)

        if self.replies:
            if self._reply_index < len(self.replies):
                r = self.replies[self._reply_index]
                self._reply_index += 1
                return r
            return self.replies[-1]      # 用完了就重复最后一条

        for keyword, reply in self.rules.items():
            if keyword in prompt:
                return reply

        return f"[模拟回复] {prompt}"

    def _record(self, kind: str, **fields) -> None:
        self.calls.append({"type": kind, **fields})

    # ------------------------------------------------------------------
    # 与 ZhipuClient 对应的方法
    # ------------------------------------------------------------------

    def chat(self, prompt, system=None, temperature=None, **kwargs) -> str:
        reply = self._make_reply(prompt, system)
        self._record("chat", prompt=prompt, system=system,
                     temperature=temperature, reply=reply)
        return reply

    def chat_messages(self, messages, temperature=None, **kwargs) -> str:
        last = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        system = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )
        reply = self._make_reply(last, system)
        self._record("chat_messages", messages=list(messages),
                     turns=len(messages), temperature=temperature, reply=reply)
        return reply

    def chat_raw(self, messages, **kwargs) -> dict:
        reply = self.chat_messages(messages, **kwargs)
        return {
            "choices": [{"message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    def stream(self, prompt, system=None, temperature=None, **kwargs):
        reply = self._make_reply(prompt, system)
        self._record("stream", prompt=prompt, system=system, reply=reply)
        for ch in reply:
            yield ch

    def stream_messages(self, messages, temperature=None, **kwargs):
        reply = self.chat_messages(messages, temperature=temperature)
        for ch in reply:
            yield ch

    def embed(self, texts, model=None):
        items = texts if isinstance(texts, list) else [texts]
        self._record("embed", count=len(items))
        return [[0.0] * 8 for _ in items]

    def image(self, prompt, model=None):
        self._record("image", prompt=prompt)
        return "https://example.invalid/mock.png"

    # ------------------------------------------------------------------
    # 断言辅助
    # ------------------------------------------------------------------

    @property
    def prompts(self) -> list[str]:
        """所有发出去的提示词，按顺序。"""
        return [c["prompt"] for c in self.calls if "prompt" in c]

    def called(self, times: int | None = None) -> bool:
        """是否被调用过；给 times 则检查次数。"""
        return len(self.calls) == times if times is not None else bool(self.calls)

    def reset(self) -> None:
        self.calls.clear()
        self._reply_index = 0
