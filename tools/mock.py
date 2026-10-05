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

    # 几个词都出现才算命中（按顺序找第一条），都不中给 default
    MockClient(rules=[{"when": ["判断意图", "出几道"], "reply": '{"intent":"出题"}'},
                      {"when": ["老师"], "reply": "好的"}], default="嗯")

    # 同样的规则写在 JSON 文件里：{"rules": [...], "default": "..."}。
    # 起服务做浏览器测试时，环境变量 DSL_MOCK_SCRIPT 指向它（见 from_env）
    MockClient.from_file("mock.json")

离线（offline=True）：所有调用都交给这个假客户端，不按模型名分派——不写的话
「用 快」解析成 cli:claude/haiku 时，外面那层路由（llm_router）会真去起
claude -p。gen run 不带 --real 起的服务用的就是离线的假客户端。收到的 model
原样记在 calls 里：解析过的名字（如 cli:claude/haiku），从档位查到的还带着
tier（"快"），测「这一句用的是哪一档」看它。
"""

import json
import os


class MockClient:
    """假的智谱客户端，用于离线测试 DSL 脚本。"""

    def __init__(self, replies=None, rules=None, handler=None,
                 model="mock-model", default=None, offline=False):
        self.model = model
        self.default_temperature = 0.7
        self.embedding_model = "mock-embedding"
        self.image_model = "mock-image"

        self.replies = list(replies) if replies else []
        self.rules = rules or {}
        self.handler = handler
        self.default = default
        self.offline = offline

        self.calls: list[dict] = []      # 每次调用的完整记录
        # 最后一次对话调用收到的 model 参数（原样，没传就是 None），
        # 测「模型 X」「用 X」有没有传到客户端用
        self.last_model = None
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

        text = prompt + "\n" + (system or "")
        if isinstance(self.rules, dict):
            for keyword, reply in self.rules.items():
                if keyword in prompt:
                    return reply
        else:
            for r in self.rules:
                words = r.get("when") or []
                if isinstance(words, str):
                    words = [words]
                if all(w in text for w in words):
                    return r.get("reply", "")

        if self.default is not None:
            return self.default
        return f"[模拟回复] {prompt}"

    @classmethod
    def from_file(cls, path, **kw):
        """从 JSON 文件读规则：{"rules": [{"when": [...], "reply": "..."}],
        "default": "..."}。rules 也可以是 {关键词: 回复} 的旧写法。"""
        data = json.loads(open(path, encoding="utf-8").read())
        return cls(rules=data.get("rules") or {}, default=data.get("default"),
                   **kw)

    @classmethod
    def from_env(cls, **kw):
        """环境变量 DSL_MOCK_SCRIPT 指向规则文件就按它回，没设就是默认的假回复。"""
        path = os.environ.get("DSL_MOCK_SCRIPT")
        if path:
            return cls.from_file(path, **kw)
        return cls(**kw)

    def _record(self, kind: str, **fields) -> None:
        # model 是 ModelRef（str 的子类）时把档位一起记下来，存成普通字符串
        m = fields.get("model")
        if m is not None:
            fields["tier"] = getattr(m, "tier", None)
            fields["model"] = str(m)
        self.calls.append({"type": kind, **fields})

    # ------------------------------------------------------------------
    # 与 ZhipuClient 对应的方法
    # ------------------------------------------------------------------

    def chat(self, prompt, system=None, temperature=None, model=None,
             **kwargs) -> str:
        self.last_model = model
        reply = self._make_reply(prompt, system)
        self._record("chat", prompt=prompt, system=system,
                     temperature=temperature, model=model, reply=reply)
        return reply

    def chat_messages(self, messages, temperature=None, model=None,
                      **kwargs) -> str:
        self.last_model = model
        last = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        system = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )
        reply = self._make_reply(last, system)
        self._record("chat_messages", messages=list(messages),
                     turns=len(messages), temperature=temperature,
                     model=model, reply=reply)
        return reply

    def chat_raw(self, messages, model=None, **kwargs) -> dict:
        reply = self.chat_messages(messages, model=model, **kwargs)
        return {
            "choices": [{"message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    def stream(self, prompt, system=None, temperature=None, model=None,
               **kwargs):
        self.last_model = model
        reply = self._make_reply(prompt, system)
        self._record("stream", prompt=prompt, system=system, model=model,
                     reply=reply)
        for ch in reply:
            yield ch

    def stream_messages(self, messages, temperature=None, model=None,
                        **kwargs):
        reply = self.chat_messages(messages, temperature=temperature,
                                   model=model)
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
        self.last_model = None
