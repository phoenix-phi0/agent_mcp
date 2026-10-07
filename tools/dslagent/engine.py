"""AgentEngine：DSLEngine 的子类，给 dslagent 用。比基类多三件事，都不改基类、不打全局补丁：

- 系统子脚本不进项目：「执行 定位.zs / 读改测.zs / _plan/名字.zs」映射到 dslagent/lib 和任务目录里的计划，
  项目目录里不放任何临时脚本（实验装置是拷进项目再删，崩了会留垃圾）。
- 语句白名单：计划里只许用 ALLOWED_HEADS 里的语句（静态检查之外的运行期兜底，子引擎同样生效）。
- 子脚本调用记录：on_call 回调拿到每次 定位.zs / 读改测.zs 的参数、耗时和返回的 outcome/log。
"""
import time

from tools.dsl import DSLEngine, DSLError

ALLOWED_HEADS = {"use", "set", "ask", "ask_json", "if", "elif", "else", "end", "each", "print", "compute", "call", "ret"}
LIB_SCRIPTS = ("定位.zs", "读改测.zs")


class AgentEngine(DSLEngine):
    def __init__(self, *a, scripts=None, guard=True, on_call=None, **k):
        super().__init__(*a, **k)
        self.scripts = dict(scripts or {})
        self.guard = guard
        self.on_call = on_call

    def _sub_engine(self):
        sub = AgentEngine(client=self.client, workdir=self.workdir, verbose=False, verbs=self.verbs,
                          verbs_root=self.verbs_root, _depth=self._depth + 1,
                          scripts=self.scripts, guard=self.guard, on_call=self.on_call)
        sub.system = self.system
        sub.temperature = self.temperature
        sub.model = self.model
        sub.strict_verbs = self.strict_verbs
        return sub

    def _safe_path(self, name):
        key = str(name).strip()
        if key in self.scripts:
            return self.scripts[key]
        return super()._safe_path(name)

    def _exec_stmt(self, head, rest, lineno=-1):
        if self.guard and head not in ALLOWED_HEADS:
            raise DSLError(f"第 {lineno + 1} 行：语句「{head}」不在白名单里（dslagent 拦截）")
        return super()._exec_stmt(head, rest, lineno)

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
