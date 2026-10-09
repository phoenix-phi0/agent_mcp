"""「预算 调用 N 秒 M」：整个流程的模型调用次数和墙钟秒数上限。

引擎从顶层 run() 开始计：模型调用数（问、问JSON 及其重问、流式、对话、判定、
带工具的每一轮、派任务 / 并行派任务里的每一次、子脚本里的）和墙钟秒数。计数
在客户端外面套的一层 CountingClient 上做，所以不管哪条路调模型都算得到；子引擎
（执行 子.zs、.zs 动词、后台执行）拿的是父引擎这个客户端，共用同一份 Usage。

超出时按「终止 超出预期 预算用完：…」结束：
- 第 N+1 次调模型时直接拦下（不发出去），抛 ScriptHalt；
- 墙钟在每条语句开头查，也在每次调模型之前查（一次慢调用中途打断不了）。
拦下之后 Usage 记着「用完了」：子脚本里拦下只结束子脚本，回到调用方的下一条语句
照样终止，不会接着跑。
"""
import threading
import time

from .dsl_core import ScriptHalt

MODEL_METHODS = ("chat", "chat_messages", "chat_raw", "chat_json", "chat_json_messages",
                 "stream", "stream_messages")


class Usage:
    """一个流程的用量和上限。线程安全（并行派任务、后台执行会并发调模型）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.calls = 0
            self.t0 = time.monotonic()
            self.max_calls: int | None = None
            self.max_secs: int | None = None
            self.spent = ""          # 拦下过一次就记着原因

    @property
    def limited(self) -> bool:
        return self.max_calls is not None or self.max_secs is not None

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def set_limits(self, calls: int | None, secs: int | None) -> None:
        with self._lock:
            if calls is not None:
                self.max_calls = calls
            if secs is not None:
                self.max_secs = secs

    def over(self) -> str:
        """用完了就返回原因（不带「预算用完：」），没用完返回空串。"""
        if self.spent:
            return self.spent
        if self.max_secs is not None and self.elapsed() > self.max_secs:
            return f"已用 {self.elapsed():.1f} 秒，上限 {self.max_secs} 秒"
        if self.max_calls is not None and self.calls > self.max_calls:
            return f"模型调用已用 {self.calls} 次，上限 {self.max_calls} 次"
        return ""

    def take(self) -> None:
        """调模型之前记一次；超出上限抛 ScriptHalt（停在哪一行由引擎补）。"""
        with self._lock:
            why = self.spent
            if not why and self.max_secs is not None and self.elapsed() > self.max_secs:
                why = f"已用 {self.elapsed():.1f} 秒，上限 {self.max_secs} 秒"
            if not why and self.max_calls is not None and self.calls >= self.max_calls:
                why = f"模型调用已用 {self.calls} 次，上限 {self.max_calls} 次，第 {self.calls + 1} 次没有发出"
            if why:
                self.spent = why
                raise ScriptHalt("超出预期", f"预算用完：{why}", "")
            self.calls += 1


class CountingClient:
    """包住引擎的客户端：调模型的方法先过 Usage.take()，别的属性读写都转给里面那层。"""

    def __init__(self, inner, usage: Usage):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "usage", usage)

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name not in MODEL_METHODS or not callable(attr):
            return attr

        def counted(*a, **k):
            self.usage.take()
            return attr(*a, **k)
        return counted

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)
