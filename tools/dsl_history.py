# -*- coding: utf-8 -*-
"""对话历史那一组：重置、读历史、存历史、修剪历史。

从 dsl.py 拆出来的第三块，同样是混进 DSLEngine 的 mixin。

依赖的引擎属性：self.history、self.system、self._emit、self.expand、
self._safe_path、self._rel。

## 为什么历史需要显式管理

「对话」每次把全部历史发出去，**引擎不自动裁剪**。挂了文件的那条尤其
大，之后每轮重发；工具调用的中间消息也在里面。二十轮之后一次请求就带
二十轮内容。

所以「修剪历史」不是可选的。需要长期记忆的话，把要点提炼成文字塞进
「系统」，而不是留着原始对话。
"""

import json

from .dsl_core import DSLError, msg_size, parse_trim_spec


class HistoryMixin:
    """多轮对话历史的读写与修剪。混进 DSLEngine。"""

    def _ensure_system(self) -> None:
        """确保 system 在历史最前面。

        判断的是「有没有 system 角色」而不是「历史空不空」：读回历史后
        历史非空，但里面可能没有 system——那时这次设的系统提示词就永远
        加不进去了。这是个真出现过的 bug。
        """
        if self.system and not any(m.get("role") == "system"
                                   for m in self.history):
            self.history.insert(0, {"role": "system", "content": self.system})

    def _do_load_history(self, rest: str) -> None:
        path = self._safe_path(self.expand(rest.strip()))
        # 不存在不报错：第一次跑本来就没有历史，报错的话每个脚本都要
        # 先判断一次文件在不在
        if not path.is_file():
            self.history = []
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise DSLError(f"{self._rel(path)} 不是合法 JSON："
                           f"第 {e.lineno} 行 {e.msg}") from e
        if not isinstance(data, list):
            raise DSLError(f"{self._rel(path)} 里不是消息列表")
        # 坏数据跳过而不是整个作废——历史是累积出来的，一条坏了不该让
        # 之前几十轮全丢
        self.history = [m for m in data if isinstance(m, dict)
                        and m.get("role") and "content" in m]

    def _do_save_history(self, rest: str) -> None:
        path = self._safe_path(self.expand(rest.strip()))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.history, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        total = sum(msg_size(m) for m in self.history)
        # 报字数不只报条数：历史涨到多大是看不见的，而 token 是按字算的
        self._emit(f"[已存历史 {self._rel(path)}，{len(self.history)} 条，"
                   f"约 {total} 字]")

    def _do_trim_history(self, rest: str, lineno: int) -> None:
        """修剪历史 [条数] [字数字] —— 两个上限都满足，谁先触发听谁的。"""
        keep_n, keep_chars = parse_trim_spec(self.expand(rest).strip(), lineno)

        # system 单独保住：它是人设，掉了模型就变个人。
        # 也不算进字数预算——预算是给对话用的，人设是固定开销。
        sys_msgs = [m for m in self.history if m.get("role") == "system"]
        talk = [m for m in self.history if m.get("role") != "system"]
        before = len(talk)

        if keep_n is not None:
            talk = talk[-keep_n:] if keep_n > 0 else []

        if keep_chars is not None:
            kept, used = [], 0
            # 从最近的往回收：新的比旧的重要。至少留一条，否则挂了大
            # 文件之后历史会被整个清空。
            for m in reversed(talk):
                size = msg_size(m)
                if kept and used + size > keep_chars:
                    break
                kept.append(m)
                used += size
            talk = list(reversed(kept))

        self.history = sys_msgs + talk
        dropped = before - len(talk)
        if dropped > 0:
            total = sum(msg_size(m) for m in self.history)
            self._emit(f"[修剪历史 丢弃 {dropped} 条，"
                       f"剩余 {len(self.history)} 条约 {total} 字]")
