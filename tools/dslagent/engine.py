"""AgentEngine：DSLEngine 的子类，给 dslagent 用（v2 和旧路径共用）。比基类多三件事，都不改基类、不打全局补丁：

- 系统子脚本不进项目：「执行 _plan/名字.zs」映射到任务目录里的计划，项目目录里不放任何临时脚本
  （实验装置是拷进项目再删，崩了会留垃圾）。
- 语句白名单：计划里只许用 ALLOWED_HEADS 里的语句（静态检查之外的运行期兜底，子引擎同样生效）。
- 子任务 tool 模式：run_subtask_tool → toolsub.py。
旧路径专用的（定位.zs / 读改测.zs 调用记录、固定系统提示）在 legacy/engine.py 的 LegacyEngine。
"""
import sys

from tools.dsl import DSLEngine, DSLError

WRITE_VERBS = ("改文件", "写文件", "删文件")     # 会过安全约束（reason.check）的动词
ALLOWED_HEADS = {"use", "set", "ask", "ask_json", "if", "elif", "else", "end", "each", "print", "compute", "call", "ret",
                 "while", "repeat", "break", "continue", "halt", "budget"}


class AgentEngine(DSLEngine):
    lazy_reason = False        # True：第一次真的要写 / 改 / 删文件之前才给安全约束设开局快照（v2 用；旧路径开局就设）

    def __init__(self, *a, scripts=None, guard=True, **k):
        super().__init__(*a, **k)
        self.scripts = dict(scripts or {})
        self.guard = guard
        self.subtask_mode = "json"
        self.sublog = None

    def _sub_engine(self):
        sub = AgentEngine(client=self.client, workdir=self.workdir, verbose=False, verbs=self.verbs,
                          verbs_root=self.verbs_root, _depth=self._depth + 1,
                          scripts=self.scripts, guard=self.guard)
        sub.system = self.system
        sub.temperature = self.temperature
        sub.model = self.model
        sub.strict_verbs = self.strict_verbs
        sub.dry_run = self.dry_run
        sub.subtask_mode = self.subtask_mode
        sub.sublog = self.sublog
        sub.lazy_reason = self.lazy_reason
        return sub

    def _reason_setup(self):
        """第一次真的要 改文件 / 写文件 / 删文件 时（还没改过任何东西）才给安全约束（reason.check）开局快照：
        覆盖任务没点名的数据文件、删仍被引用的文件、数据迁移不等价这些规则要靠它。整个运行只做一次（子引擎看到 STATE 里有快照就跳过）。"""
        from . import reason as R
        if not R.enabled() or R.STATE.get("snap") is not None:
            return
        sys.modules["dslagent_reason"] = R          # 动词（推理.py 的 _R）按这个名字取模块
        R.setup(self.workdir, R.all_files(self.workdir), str(self.vars.get("task") or ""))

    def _do_verb(self, name, rest, lineno, assign_to=None):
        if self.lazy_reason and name in WRITE_VERBS and not self.dry_run:
            self._reason_setup()
        return super()._do_verb(name, rest, lineno, assign_to)

    def run_subtask_tool(self, task, inputs, logic, spec):
        from . import toolsub
        return toolsub.run(self, task, inputs, logic, spec)

    def _safe_path(self, name):
        key = str(name).strip()
        if key in self.scripts:
            return self.scripts[key]
        return super()._safe_path(name)

    def _exec_stmt(self, head, rest, lineno=-1):
        if self.guard and head not in ALLOWED_HEADS:
            raise DSLError(f"第 {lineno + 1} 行：语句「{head}」不在白名单里（dslagent 拦截）")
        return super()._exec_stmt(head, rest, lineno)
