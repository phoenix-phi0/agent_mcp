"""Agent 基类：加载 SOUL.md 作为系统提示词，跑工具调用循环。

    from agents import Agent
    from agents.builtin import make_file_tools

    agent = Agent(
        soul="agents/souls/JP-E01-pi.md",
        workspace="workspace/japanese",
        tools=make_file_tools("workspace/japanese"),
    )
    print(agent.send("你好"))
"""

import json
from pathlib import Path

from .registry import Registry, describe

# 回传给接口时保留的字段。推理模型（glm-4.6 等）还会返回
# reasoning_content，那是思考过程，不该回传——既可能被接口拒绝，
# 也白白占 token。
KEEP_FIELDS = ("role", "content", "tool_calls")


def clean_message(message: dict) -> dict:
    """只保留可以回传的字段。"""
    return {k: v for k, v in message.items() if k in KEEP_FIELDS}


class Agent:
    def __init__(
        self,
        soul: str | Path,
        workspace: str | Path,
        tools: Registry | None = None,
        client=None,
        max_rounds: int = 8,
        extra_system: str = "",
        verbose: bool = False,
        model: str | None = None,
    ):
        self.soul_path = Path(soul)
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

        if not self.soul_path.is_file():
            raise FileNotFoundError(f"找不到 SOUL 文件：{self.soul_path}")
        self.soul = self.soul_path.read_text(encoding="utf-8")

        self.tools = tools or Registry()
        self.max_rounds = max_rounds
        self.verbose = verbose
        self.extra_system = extra_system

        self._client = client
        # 这个 agent 用的模型（规范名 api:zhipu/… / cli:claude/…、裸名、档位或别名），
        # 每次调用传给客户端，不改共用客户端的 client.model。None = 默认
        self.model = model
        self.messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        self.tool_log: list[dict] = []
        self.usage: dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
        self.last_reasoning: str = ""

    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        parts = [self.soul]
        if self.tools.names():
            parts.append(
                "\n---\n## 可用工具\n"
                + describe(self.tools)
                + "\n\n所有文件路径都相对于工作目录，不要使用绝对路径。"
            )
        if self.extra_system:
            parts.append("\n---\n" + self.extra_system)
        return "\n".join(parts)

    @property
    def client(self):
        if self._client is None:
            from tools import ZhipuClient
            self._client = ZhipuClient()
        # 按模型的通道分派：cli:claude/… / cli:zcode 走本机 CLI。带工具时
        # chat_raw 收到 tools，路由据此按能力表检查（cli 不支持，档位有
        # fallback 就改用 fallback），见 tools/llm_router.py
        from tools.llm_router import wrap
        self._client = wrap(self._client)
        return self._client

    def _log(self, *args) -> None:
        if self.verbose:
            print(*args)

    def _track_usage(self, data: dict) -> None:
        u = data.get("usage") or {}
        self.usage["prompt"] += u.get("prompt_tokens", 0)
        self.usage["completion"] += u.get("completion_tokens", 0)
        self.usage["total"] += u.get("total_tokens", 0)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def send(self, user_input: str, temperature: float = 0.6) -> str:
        """发一条用户消息，处理完所有工具调用后返回最终回复。"""
        self.messages.append({"role": "user", "content": user_input})
        return self._loop(temperature)

    def _loop(self, temperature: float) -> str:
        schemas = self.tools.schemas()

        for round_no in range(self.max_rounds):
            kwargs = {"temperature": temperature, "model": self.model}
            if schemas:
                kwargs["tools"] = schemas
                kwargs["tool_choice"] = "auto"

            data = self.client.chat_raw(self.messages, **kwargs)
            self._track_usage(data)

            raw = data["choices"][0]["message"]
            # 推理内容留作调试用，但不回传
            if raw.get("reasoning_content"):
                self.last_reasoning = raw["reasoning_content"]
                self._log(f"  [思考] {self.last_reasoning[:100]}")

            message = clean_message(raw)
            self.messages.append(message)

            calls = message.get("tool_calls")
            if not calls:
                return message.get("content") or ""

            self._log(f"[第{round_no + 1}轮] 调用 {len(calls)} 个工具")

            for call in calls:
                fn = call["function"]
                name, args = fn["name"], fn.get("arguments", "{}")
                self._log(f"  → {name}({args[:80]})")

                result = self.tools.call(name, args)
                self.tool_log.append(
                    {"round": round_no + 1, "name": name,
                     "arguments": args, "result": result[:500]}
                )
                self._log(f"  ← {result[:80]}")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result,
                })

        return f"[达到最大轮数 {self.max_rounds}，可能陷入循环]"

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """清空对话历史，保留系统提示词。"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.tool_log.clear()
        self.last_reasoning = ""

    def transcript(self) -> str:
        """把对话导出成可读文本，调试用。"""
        lines = []
        for m in self.messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "tool":
                lines.append(f"[工具结果] {m['content'][:200]}")
            elif m.get("tool_calls"):
                for c in m["tool_calls"]:
                    fn = c["function"]
                    lines.append(
                        f"[调用] {fn['name']}({fn.get('arguments', '')[:120]})"
                    )
            elif m.get("content"):
                who = "用户" if role == "user" else "助手"
                lines.append(f"{who}：{m['content']}")
        return "\n".join(lines)

    def dump_state(self) -> str:
        """当前状态摘要。"""
        return json.dumps({
            "soul": str(self.soul_path.name),
            "workspace": str(self.workspace),
            "工具": self.tools.names(),
            "对话轮数": len([m for m in self.messages if m.get("role") == "user"]),
            "工具调用次数": len(self.tool_log),
            "累计 token": self.usage,
        }, ensure_ascii=False, indent=2)
