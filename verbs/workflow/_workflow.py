# -*- coding: utf-8 -*-
"""缩进式多角色任务编排，由 workflow 包的「编排执行」动词调用。"""
import json
import os
import re
import time
from pathlib import Path

from tools.dsl_core import DSLError, to_text

_TASK_FIELDS = {"任务", "角色", "文本", "记录", "格式"}
_JUMP = re.compile(r"^跳转\s+(\w+)\s+最大\s+(\d+)\s*$")
_LABEL = re.compile(r"^标记\s*:\s*(\w+)\s*$")
_EACH = re.compile(r"^遍历\s+(\w+)\s+于\s+(.+)$")
_STORE = re.compile(r"^存储\s+(\w+)\s+(.+)$")
_REF = re.compile(r"^[\w]+(?:\.[\w]+)*$")


def parse(script):
    rows = []
    for n, raw in enumerate(script.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise DSLError(f"第 {n} 行：缩进请使用空格")
        rows.append((len(raw) - len(raw.lstrip()), raw.strip(), n))
    if rows and rows[0][0]:
        raise DSLError(f"第 {rows[0][2]} 行：顶层语句不能缩进")

    def block(pos, level):
        out = []
        while pos < len(rows) and rows[pos][0] == level:
            _, line, n = rows[pos]
            pos += 1
            children = []
            if pos < len(rows) and rows[pos][0] > level:
                children, pos = block(pos, rows[pos][0])
            out.append((line, n, children))
        if pos < len(rows) and rows[pos][0] > level:
            raise DSLError(f"第 {rows[pos][2]} 行：缩进层级不一致")
        return out, pos

    return block(0, 0)[0] if rows else []


class _Trace:
    """编排过程记录。每走一步追加一条事件，立刻整份写回 JSON（先写临时文件再替换），
    所以中途出错、进程被杀，已经走过的步骤也留在文件里。空跑（dry_run）不写文件。

    文件：<工作目录>/runs/<YYYYmmdd-HHMMSS>-<脚本名>.json，同一秒重名加 -2、-3。
    """

    def __init__(self, engine, name, script, path=None, keep=None):
        self.path = None
        self._t0 = time.time()
        refs = sorted(set(re.findall(r"\{(\w+)\}", script)))
        self.data = {
            "workflow": name, "workdir": str(engine.workdir), "status": "running",
            "started": _stamp(), "finished": None, "seconds": None, "error": None,
            "inputs": {k: engine.lookup(k) for k in refs if engine.lookup(k) is not None},
            "script": script, "pid": os.getpid(), "updated": None, "events": []}
        if keep:
            # 回放：同一份文件从头重写，开始时间沿用，记一次第几回继续
            self.data["started"] = keep.get("started", self.data["started"])
            self.data["resumes"] = keep.get("resumes", 0) + 1
        if path is not None:
            self.path = Path(path)
        elif not getattr(engine, "dry_run", False):
            folder = Path(engine.workdir) / "runs"
            folder.mkdir(parents=True, exist_ok=True)
            base = time.strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"[^\w.-]", "_", name)
            path, i = folder / f"{base}.json", 1
            while path.exists():
                i += 1
                path = folder / f"{base}-{i}.json"
            self.path = path
        self.save()

    def add(self, **event):
        event = {"seq": len(self.data["events"]) + 1, **event}
        self.data["events"].append(event)
        self.save()
        return event

    def update(self, event, **fields):
        """原地改一条已经写进去的事件（任务从 running 变成 ok/error 时用）。"""
        event.update(fields)
        self.save()
        return event

    def finish(self, status, error=None):
        self.data.update(status=status, error=error, finished=_stamp(),
                         seconds=round(time.time() - self._t0, 1))
        self.save()

    def save(self):
        if self.path is None:
            return
        self.data["updated"] = _stamp()
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        os.replace(tmp, self.path)


def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run(engine, script, call_agent, name="workflow", describe=None, load_format=None,
        check_format=None):
    """engine._wf_control 有值时，每个任务节点怎么跑由外部决定（见 tools/workflow_ctl.py）：
    回放记录里的结果、用外部交来的结果、按默认或覆盖的模型/角色卡跑，或者停下等待。"""
    nodes = parse(script)
    ctl = getattr(engine, "_wf_control", None)
    if ctl is not None:
        ctl.claim()
    trace = _Trace(engine, name, script, path=ctl.path if ctl else None,
                   keep=ctl.old if ctl else None)
    if ctl is not None:
        ctl.attach(trace)
    steps = [0]
    engine.store("workflow_trace", str(trace.path) if trace.path else "")
    labels = {}
    jumps = {}
    for i, (line, n, children) in enumerate(nodes):
        m = _LABEL.fullmatch(line)
        if m:
            if children or m[1] in labels:
                raise DSLError(f"第 {n} 行：标记重复或带有子块：{m[1]}")
            labels[m[1]] = i

    def resolve(raw):
        raw = raw.strip()
        if raw.startswith("{") and raw.endswith("}") and raw.count("{") == 1:
            value = engine.lookup(raw[1:-1])
            if value is not None:
                return value
        if _REF.fullmatch(raw):
            value = engine.lookup(raw)
            if value is not None:
                return value
        return engine.expand(raw)

    def execute(nodes):
        for line, n, children in nodes:
            engine._at = n - 1
            if engine.usage.limited:
                spent = engine.usage.over()
                if spent:
                    raise DSLError(f"第 {n} 行：预算用完：{spent}")
            if _LABEL.fullmatch(line):
                if children:
                    raise DSLError(f"第 {n} 行：标记不能带子块")
                continue
            m = _JUMP.fullmatch(line)
            if m:
                if children:
                    raise DSLError(f"第 {n} 行：跳转不能带子块")
                target, max_count = m[1], int(m[2])
                if target not in labels or not 1 <= max_count <= 1000:
                    raise DSLError(f"第 {n} 行：跳转目标或最大次数无效")
                jumps[n] = jumps.get(n, 0) + 1
                if jumps[n] > max_count:
                    raise DSLError(f"第 {n} 行：跳转 {target} 超过最大 {max_count} 次")
                trace.add(type="jump", line=n, target=target, count=jumps[n], max=max_count)
                raise _Jump(target)
            if line.startswith("如果 "):
                if not children:
                    raise DSLError(f"第 {n} 行：如果缺少子块")
                cond = re.sub(r"(?<![\w{])([A-Za-z_][\w]*(?:\.[\w]+)+)(?![\w}])",
                              lambda x: "{" + x[1] + "}", line[3:])
                ok = bool(engine._eval_condition(cond, n - 1))
                trace.add(type="if", line=n, cond=line[3:].strip(), value=ok)
                if ok:
                    execute(children)
                continue
            m = _EACH.fullmatch(line)
            if m:
                if not children:
                    raise DSLError(f"第 {n} 行：遍历缺少子块")
                items = resolve(m[2])
                if not isinstance(items, list):
                    raise DSLError(f"第 {n} 行：遍历需要列表：{m[2]}")
                trace.add(type="each", line=n, var=m[1], source=m[2].strip(), count=len(items))
                for item in items:
                    engine.store(m[1], item)
                    execute(children)
                continue
            m = _STORE.fullmatch(line)
            if m:
                if children:
                    raise DSLError(f"第 {n} 行：存储不能带子块")
                old = engine.lookup(m[1])
                if old is None:
                    old = []
                    engine.store(m[1], old)
                if not isinstance(old, list):
                    raise DSLError(f"第 {n} 行：{m[1]} 不是列表")
                old.append(resolve(m[2]))
                trace.add(type="store", line=n, target=m[1], size=len(old))
                continue
            if children:
                fields = {}
                for child_line, child_n, grandchildren in children:
                    key, sep, value = child_line.partition(" ")
                    if grandchildren or not sep or key not in _TASK_FIELDS or key in fields:
                        raise DSLError(f"第 {child_n} 行：任务块只能包含任务、角色、文本、记录、格式各一项")
                    fields[key] = value.strip()
                if not all(fields.get(x) for x in ("角色", "记录")):
                    raise DSLError(f"第 {n} 行：任务块需要角色、记录")
                record = fields["记录"]
                if not _REF.fullmatch(record) or "." in record:
                    raise DSLError(f"第 {n} 行：记录名无效：{record}")
                task, role = to_text(resolve(fields.get("任务", line))), to_text(resolve(fields["角色"]))
                context = resolve(fields["文本"]) if fields.get("文本") else None
                fmt = None
                if fields.get("格式"):
                    if load_format is None:
                        raise DSLError(f"第 {n} 行：这个执行器不支持「格式」")
                    fmt = load_format(engine, fields["格式"])
                steps[0] += 1
                request = dict(step=steps[0], line=n, name=line, role=role, task=task,
                               context=context, record=record)
                if fmt:
                    request["format"] = fmt[0]
                # 只在用到时才多传参数：别的执行器（测试里的假 call_agent）签名不用跟着改
                extra = {"node": line, "fmt": fmt} if fmt else {}
                decision = ctl.decide(request) if ctl is not None else {"action": "run"}
                action = decision["action"]
                # 这一步以前失败过的尝试原样留在记录里（回放时控制器交回来）
                for failed in decision.get("failed", []):
                    trace.add(**{k: v for k, v in failed.items() if k != "seq"})

                def stop(use_role, use_model, last_error=None):
                    """停在这一步等外部：记一条 waiting 事件，pending 里放完整请求。"""
                    pending = dict(request, card=use_role)
                    if last_error:
                        pending["last_error"] = last_error
                    if describe is not None:
                        try:
                            pending.update(describe(engine, use_role, task, context, model=use_model, **extra))
                        except Exception as e:      # 卡坏了也照样停下，让外部看到原因、换卡
                            pending["card_error"] = str(e)
                    trace.add(type="task", **request, status="waiting")
                    trace.data.update(status="waiting", pending=pending)
                    trace.save()
                    raise ctl.pause()

                if action == "replay":
                    old = {k: v for k, v in decision["event"].items() if k != "seq"}
                    trace.add(**old)
                    engine.store(record, old["result"])
                    continue
                if action == "result":
                    bad = check_format(fmt, decision["result"]) if fmt and check_format else []
                    if bad:
                        raise DSLError(f"第 {n} 行：外部交的结果不符合格式 {fmt[0]}：" + "；".join(bad[:5]))
                    trace.add(type="task", **request, started=_stamp(), status="ok", source="external",
                              model="external", seconds=0.0, result=decision["result"])
                    engine.store(record, decision["result"])
                    continue
                use_role = decision.get("role") or role
                use_model = decision.get("model")
                if action == "wait":
                    stop(use_role, use_model)
                if action != "run":
                    raise DSLError(f"第 {n} 行：外部控制给了未知动作：{action}")
                t0, started = time.time(), _stamp()
                event = dict(type="task", **request, started=started)
                if use_role != role:
                    event.update(role=use_role, default_role=role)
                if decision.get("by"):
                    event["source"] = decision["by"]
                if use_model:
                    event["model_override"] = use_model
                # 先写一条进行中的事件：查看器在调用期间就能看到停在哪一步
                ev = trace.add(**event, status="running")
                engine._wf_last_call = {}
                engine._wf_on_call = lambda meta: trace.update(ev, **meta)
                try:
                    kw = dict(extra, model=use_model) if use_model else extra
                    result = call_agent(engine, use_role, task, context, **kw)
                except Exception as e:
                    trace.update(ev, **getattr(engine, "_wf_last_call", {}), status="error",
                                 error=str(e), seconds=round(time.time() - t0, 1))
                    if ctl is not None:
                        # 受控时节点失败不结束编排：停在这一步，外部决定重试、换模型换卡还是手交结果
                        stop(use_role, use_model, last_error=str(e))
                    raise
                finally:
                    engine._wf_on_call = None
                trace.update(ev, **getattr(engine, "_wf_last_call", {}), status="ok",
                             result=result, seconds=round(time.time() - t0, 1))
                engine.store(record, result)
                continue
            raise DSLError(f"第 {n} 行：看不懂的编排语句：{line}")

    class _Jump(Exception):
        def __init__(self, target):
            self.target = target

    pc = 0
    try:
        while pc < len(nodes):
            try:
                execute([nodes[pc]])
            except _Jump as jump:
                pc = labels[jump.target]
            else:
                pc += 1
    except BaseException as e:
        if getattr(e, "wf_pause", False):
            raise
        trace.finish("error", f"{type(e).__name__}: {e}")
        raise
    trace.data.pop("pending", None)
    trace.finish("done")
    return "\n".join(engine.output)
