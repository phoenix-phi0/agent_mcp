"""LegacyEngine：旧路径的引擎。在 AgentEngine 之上多两件事：

- 子脚本调用记录：on_call 回调拿到每次 定位.zs / 读改测.zs 的参数、耗时和返回的 outcome/log。
- 固定系统提示：定位.zs / 读改测.zs 的 问JSON（提示以 prompts.LOC_TAG / RCT_TAG 开头）改用 prompts.LIB_SYSTEM 作系统提示，
  并剥掉 DSL 自动附在末尾、LIB_SYSTEM 里已有的格式说明——用户消息只剩变化内容，系统提示跨调用不变能读缓存。
  格式校验和重问还是基类那一套。
"""
import time

from tools.dsl_model import _format_note

from ..engine import AgentEngine
from . import prompts as PR

LIB_SCRIPTS = ("定位.zs", "读改测.zs")


class LegacyEngine(AgentEngine):
    def __init__(self, *a, on_call=None, **k):
        super().__init__(*a, **k)
        self.on_call = on_call

    def _sub_engine(self):
        sub = super()._sub_engine()
        legacy = LegacyEngine(client=sub.client, workdir=sub.workdir, verbose=False, verbs=sub.verbs, verbs_root=sub.verbs_root,
                              _depth=sub._depth, scripts=sub.scripts, guard=sub.guard, on_call=self.on_call)
        for k in ("system", "temperature", "model", "strict_verbs", "dry_run", "subtask_mode", "sublog", "lazy_reason"):
            setattr(legacy, k, getattr(sub, k))
        return legacy

    def _do_call(self, rest, lineno, assign_to=None):
        name = (rest.split() or [""])[0]
        if not self.on_call or name not in LIB_SCRIPTS:
            return super()._do_call(rest, lineno, assign_to)
        t0 = time.time()
        item = {"name": name, "args": rest[:200]}
        try:
            super()._do_call(rest, lineno, assign_to)
        finally:
            item["sec"] = round(time.time() - t0, 1)
            v = self.vars.get(assign_to) if assign_to else None
            if isinstance(v, dict):
                item.update({k: str(v.get(k))[:600] for k in ("outcome", "rounds", "segs", "note", "log", "reason", "need")
                             if k in v})
            self.on_call(item)

    def _ask_json_format(self, prompt, spec, reasks, model, lineno):
        tail = PR.lib_tail(prompt)
        if self.system or not tail or not prompt.endswith(tail) or _format_note(spec) != tail:
            return super()._ask_json_format(prompt, spec, reasks, model, lineno)
        self.system = PR.LIB_SYSTEM
        try:
            return super()._ask_json_format(prompt[:-len(tail)], spec, reasks, model, lineno)
        finally:
            self.system = None
