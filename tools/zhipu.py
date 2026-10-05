"""智谱开放平台（bigmodel.cn）客户端。

配置来自 config.json 或环境变量，见 config.py。

用法：
    from tools import ZhipuClient

    client = ZhipuClient()                      # 读配置
    print(client.chat("你好"))

    for chunk in client.stream("写一首短诗"):    # 流式
        print(chunk, end="", flush=True)

    obj = client.chat_json("提取姓名和年龄：张三今年28")   # 结构化输出
"""

import json
import re

import requests

from . import config

# 模型很爱把 JSON 裹进代码围栏，即使提示词里说了不要。
# 开启 response_format 之后仍然可能出现，所以剥围栏这层一直留着。
FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)
# 兜底：从一坨文本里抠出第一个看着像 JSON 的片段
BRACE_RE = re.compile(r"[\[{].*[\]}]", re.S)


def strip_json(text: str) -> str:
    """把模型回复里的 JSON 部分抠出来。

    先剥代码围栏，不行再找第一个 { 或 [ 到最后一个 } 或 ] 之间的内容。
    两步都是宽容处理——模型加一句「好的，结果如下」是常态，
    为这个报错不如先试着救回来。
    """
    text = FENCE_RE.sub("", text.strip()).strip()
    if text.startswith(("{", "[")):
        return text
    m = BRACE_RE.search(text)
    return m.group(0) if m else text


class ZhipuClient:
    """智谱开放平台客户端，接口为 OpenAI 兼容格式。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        base_url: str | None = None,
    ):
        cfg = config.load()

        self.api_key = api_key or cfg.get("api_key", "")
        if not self.api_key:
            raise ValueError(
                "缺少 API Key。请在 config.json 里填 api_key，"
                "或设置环境变量 ZHIPU_API_KEY。\n"
                f"当前配置来源：{config.source()}"
            )

        self.model = model or cfg.get("model")
        self.timeout = timeout or cfg.get("timeout", 60)
        self.base_url = (base_url or cfg.get("base_url")).rstrip("/")
        self.default_temperature = cfg.get("temperature", 0.7)
        self.embedding_model = cfg.get("embedding_model", "embedding-3")
        self.image_model = cfg.get("image_model", "cogview-4")
        # 结构化输出：智谱支持 response_format={"type":"json_object"}。
        # 不是所有模型都支持，所以配置里能关——传了不支持的参数，
        # 有的模型报错，有的静默忽略，后者更难查。
        self.json_mode = cfg.get("json_mode", True)

    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _model(self, model: str | None) -> str:
        """这一次用哪个模型：传了就解析档位/别名，没传用默认（默认也可以是档位名）。

        规范名 api:zhipu/glm-5.3 换成接口要的 glm-5.3；裸名原样。别的通道
        （cli:claude/…）不该走到这里——要经 llm_router 包一层才能分派。
        """
        name = config.resolve_model(model) or config.resolve_model(self.model)
        if not name:
            return name
        spec = config.parse_model(name)
        if (spec.channel, spec.provider) != ("api", "zhipu"):
            raise config.ModelNameError(
                f"模型 {spec.canonical} 不是智谱模型，ZhipuClient 发不了；"
                f"要经 tools.llm_router.wrap 包一层才能分派到 "
                f"{spec.backend.label}")
        return spec.model

    def _post(self, path: str, payload: dict) -> dict:
        r = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers,
            json=payload,
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise RuntimeError(f"智谱接口返回 {r.status_code}: {r.text[:300]}")
        return r.json()

    # ------------------------------------------------------------------
    # 对话
    # ------------------------------------------------------------------

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        model: str | None = None,
        **kwargs,
    ) -> str:
        """单轮对话，返回回复文本。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat_messages(messages, temperature=temperature,
                                  model=model, **kwargs)

    def chat_messages(
        self,
        messages: list[dict],
        temperature: float | None = None,
        model: str | None = None,
        **kwargs,
    ) -> str:
        """多轮对话，messages 传完整历史，返回回复文本。

        kwargs 原样透传给接口，所以 response_format、tools、thinking
        这类参数直接传就行。

        model 只管这一次：可以是真名、models.json 的档位或别名，
        不传用 self.model。不改 self.model——客户端是多处共用的。
        """
        data = self._post(
            "/chat/completions",
            {
                "model": self._model(model),
                "messages": messages,
                "temperature": (
                    self.default_temperature if temperature is None else temperature
                ),
                **kwargs,
            },
        )
        return data["choices"][0]["message"]["content"]

    def chat_raw(self, messages: list[dict], model: str | None = None,
                 **kwargs) -> dict:
        """返回完整响应体，需要 usage、tool_calls 等字段时用这个。"""
        return self._post(
            "/chat/completions",
            {"model": self._model(model), "messages": messages, **kwargs},
        )

    # ------------------------------------------------------------------
    # 结构化输出
    # ------------------------------------------------------------------

    def chat_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        retries: int = 1,
        model: str | None = None,
        **kwargs,
    ):
        """要一个 JSON 对象回来，解析好再返回。

        三层保障，一层不够就下一层：

          1. response_format={"type":"json_object"} —— 模型层面约束。
             配置里 json_mode=false 可以关掉（有的模型不支持这个参数）。
          2. 剥代码围栏、抠出 {…} —— 模型加围栏或者说一句「结果如下」
             都很常见，为这个失败不值。
          3. 重试并把要求说死 —— 还不行才抛异常。

        为什么不静默返回空对象：后面 {决策.意图} 取不到会原样保留成
        「{决策.意图}」，那个字符串扔进条件判断只会一路走到「否则」，
        错得很隐蔽。宁可报错。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat_json_messages(
            messages, temperature=temperature, retries=retries, model=model,
            **kwargs)

    def chat_json_messages(
        self,
        messages: list[dict],
        temperature: float | None = None,
        retries: int = 1,
        model: str | None = None,
        **kwargs,
    ):
        """chat_json 的多轮版本。messages 会被复制，不改调用方的列表。"""
        msgs = list(messages)
        if self.json_mode and "response_format" not in kwargs:
            kwargs["response_format"] = {"type": "json_object"}

        last = ""
        for attempt in range(retries + 1):
            try:
                last = self.chat_messages(msgs, temperature=temperature,
                                          model=model, **kwargs)
            except RuntimeError as e:
                # 模型不认 response_format 时接口会报错。摘掉它重来一次，
                # 剩下两层保障还在——总比整个失败强。
                if "response_format" in kwargs and "response_format" in str(e):
                    kwargs.pop("response_format")
                    self.json_mode = False
                    continue
                raise

            try:
                return json.loads(strip_json(last))
            except json.JSONDecodeError:
                if attempt >= retries:
                    break
                # 下一次把要求说死。追加一条 user 而不是改原提示词：
                # 模型看得到自己上次输出了什么，改起来更准。
                msgs = msgs + [
                    {"role": "assistant", "content": last},
                    {"role": "user",
                     "content": "上面不是合法 JSON。只输出 JSON 本身，"
                                "不要代码围栏，不要任何解释。"},
                ]

        raise ValueError(f"模型没有返回合法 JSON。最后一次回复：{last[:200]}")

    # ------------------------------------------------------------------
    # 流式
    # ------------------------------------------------------------------

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        model: str | None = None,
        **kwargs,
    ):
        """流式对话，逐段 yield 文本片段。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        yield from self.stream_messages(messages, temperature=temperature,
                                        model=model, **kwargs)

    def stream_messages(
        self,
        messages: list[dict],
        temperature: float | None = None,
        model: str | None = None,
        **kwargs,
    ):
        """流式多轮对话，逐段 yield 文本片段。"""
        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers,
            json={
                "model": self._model(model),
                "messages": messages,
                "stream": True,
                "temperature": (
                    self.default_temperature if temperature is None else temperature
                ),
                **kwargs,
            },
            timeout=self.timeout,
            stream=True,
        )
        if r.status_code != 200:
            raise RuntimeError(f"智谱接口返回 {r.status_code}: {r.text[:300]}")

        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            body = line[6:]
            if body == "[DONE]":
                break
            try:
                delta = json.loads(body)["choices"][0].get("delta", {})
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta.get("content"):
                yield delta["content"]

    # ------------------------------------------------------------------
    # 向量与图像
    # ------------------------------------------------------------------

    def embed(
        self,
        texts: str | list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """文本向量化，返回向量列表。"""
        data = self._post(
            "/embeddings",
            {
                "model": model or self.embedding_model,
                "input": texts if isinstance(texts, list) else [texts],
            },
        )
        return [item["embedding"] for item in data["data"]]

    def image(self, prompt: str, model: str | None = None) -> str:
        """文生图，返回图片 URL。"""
        data = self._post(
            "/images/generations",
            {"model": model or self.image_model, "prompt": prompt},
        )
        return data["data"][0]["url"]


if __name__ == "__main__":
    print("配置来源：", config.source())
    client = ZhipuClient()
    print("当前模型：", client.model)
    print("JSON 模式：", "开" if client.json_mode else "关")
    print(client.chat("用一句话介绍你自己"))
    print(client.chat_json('返回 {"ok":true,"model":"你的型号"}'))
