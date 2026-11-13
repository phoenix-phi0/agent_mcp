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
# 角色清单 roster ENGINEER_LITE ENGINEER …：读这些卡的成本和说明，存成列表给派活的节点看
# 也可以写变量：角色清单 roster {roles}，入口脚本里 设 roles = A,B,C（逗号或空格分隔）
_ROSTER = re.compile(r"^角色清单\s+(\w+)\s+([A-Za-z{][\w ,{}]*)$")
_CARD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# 成本合计 spent assignment.tasks [预算 {budget}]：按每项的 agent 查卡的成本加总，和预算比
_COST = re.compile(r"^成本合计\s+(\w+)\s+(\S+)(?:\s+预算\s+(\S+))?\s*$")


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
        # 已经花掉的成本：真跑过（成功或失败）的任务节点按卡的 cost 加总。回放的事件是原样搬回来的，
        # 带着当初的 cost，照算（那次确实花了）；外部交的结果没有 cost，不算
        costs = [e["cost"] for e in self.data["events"]
                 if e.get("type") == "task" and e.get("status") in ("ok", "error", "review", "rejected")
                 and isinstance(e.get("cost"), (int, float))]
        if costs:
            self.data["cost_spent"] = round(sum(costs), 3)
        # 实际费用：claude 自己报的（按 API 标价估算；Max 订阅不按这个计费），加上工具内部的花费。
        # 只有 claude 后端有；goose（GLM）的拿不到，计为未知
        usd = [e["usage"]["total_usd"] for e in self.data["events"]
               if e.get("type") == "task" and isinstance(e.get("usage"), dict)
               and isinstance(e["usage"].get("total_usd"), (int, float))]
        if usd:
            self.data["usd_spent"] = round(sum(usd), 4)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        os.replace(tmp, self.path)


def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run(engine, script, call_agent, name="workflow", describe=None, load_format=None,
        check_format=None, card_info=None):
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
    allowed_roles = []        # 最近一次「角色清单」的卡名；成本合计用它挡住清单外的卡
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
            m = _ROSTER.fullmatch(line) or _COST.fullmatch(line)
            if m:
                if children:
                    raise DSLError(f"第 {n} 行：{line.split()[0]}不能带子块")
                if card_info is None:
                    raise DSLError(f"第 {n} 行：这个执行器不支持{line.split()[0]}")

                def card(role):
                    try:
                        info = card_info(engine, role)
                    except DSLError as e:
                        raise DSLError(f"第 {n} 行：{e}") from e
                    if info.get("cost") is None:
                        raise DSLError(f"第 {n} 行：角色 {role} 没有配置 cost")
                    return info

                if line.startswith("角色清单"):
                    names = [x for x in re.split(r"[,\s]+", to_text(engine.expand(m[2]))) if x]
                    bad = [x for x in names if not _CARD.fullmatch(x)]
                    if bad or not names:
                        raise DSLError(f"第 {n} 行：角色清单无效（变量没设？）：{m[2]} → {names}")
                    if len(set(names)) != len(names):
                        raise DSLError(f"第 {n} 行：角色清单里有重复的角色")
                    roster = [{k: v for k, v in card(x).items() if k != "model"} for x in names]
                    allowed_roles[:] = names
                    engine.store(m[1], roster)
                    trace.add(type="roster", line=n, target=m[1], roles=roster)
                    continue
                items = resolve(m[2])
                if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
                    raise DSLError(f"第 {n} 行：成本合计需要对象列表：{m[2]}")
                budget = None
                if m[3]:
                    raw = resolve(m[3])
                    try:
                        budget = float(raw)
                    except (TypeError, ValueError):
                        raise DSLError(f"第 {n} 行：预算不是数字：{raw!r}") from None
                    if budget.is_integer():
                        budget = int(budget)
                rows, cache = [], {}
                for i, item in enumerate(items, 1):
                    role = item.get("agent")
                    if not isinstance(role, str) or not role:
                        raise DSLError(f"第 {n} 行：第 {i} 项没有 agent")
                    if role not in cache:
                        cache[role] = card(role)["cost"]
                    rows.append({"index": i, "agent": role, "cost": cache[role],
                                 "content": to_text(item.get("content", ""))})
                total = round(sum(r["cost"] for r in rows), 3)
                # 挑了角色清单外的卡（格式里列的比这次清单多）：也算超出，让分配调整换掉
                outside = sorted({r["agent"] for r in rows} - set(allowed_roles)) if allowed_roles else []
                summary = {"total": total, "budget": budget, "tasks": rows,
                           "status": "超出" if (budget is not None and total > budget) or outside else "未超出"}
                if outside:
                    summary["not_in_roster"] = outside
                engine.store(m[1], summary)
                trace.add(type="cost", line=n, target=m[1], source=m[2].strip(), total=total,
                          budget=budget, status=summary["status"], not_in_roster=outside or None,
                          by_role={r: sum(x["cost"] for x in rows if x["agent"] == r) for r in cache})
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
                # 这一步以前失败或被打回的尝试原样留在记录里。
                carry = decision.get("carry", decision.get("failed", []))
                for failed in carry:
                    trace.add(**{k: v for k, v in failed.items() if k != "seq"})
                metadata = {}
                if ctl is not None:
                    metadata["attempt"] = decision.get("attempt", len(carry) + 1)
                    if decision.get("notes"):
                        metadata["notes"] = decision["notes"]
                        extra["notes"] = decision["notes"]
                    if decision.get("confirm"):
                        metadata["confirm"] = decision["confirm"]
                    if "previous" in decision:
                        extra["previous"] = decision["previous"]

                def stop(use_role, use_model, last_error=None):
                    """停在这一步等外部：记一条 waiting 事件，pending 里放完整请求。"""
                    pending = dict(request, card=use_role, phase="before",
                                   reason="error" if last_error else decision.get("reason") or "step",
                                   attempt=metadata["attempt"] + (1 if last_error else 0),
                                   max_attempts=decision.get("max_attempts", 4),
                                   notes=decision.get("notes", []))
                    if last_error:
                        pending["last_error"] = last_error
                    if describe is not None:
                        try:
                            pending.update(describe(engine, use_role, task, context, model=use_model, **extra))
                        except Exception as e:      # 卡坏了也照样停下，让外部看到原因、换卡
                            pending["card_error"] = str(e)
                    trace.add(type="task", **request, status="waiting", attempt=pending["attempt"])
                    trace.data.update(status="waiting", pending=pending)
                    trace.save()
                    raise ctl.pause()

                def stop_after(event):
                    """review 本身就是停点：保留结果，不 store，也不另记 waiting 事件。"""
                    pending = dict(request, card=event.get("role", role), phase="after",
                                   result=event["result"], attempt=event.get("attempt", 1),
                                   max_attempts=decision.get("max_attempts", 4), model=event.get("model"),
                                   reason=decision.get("reason"), notes=decision.get("notes", []))
                    if describe is not None:
                        try:
                            pending.update(describe(engine, pending["card"], task, context,
                                                    model=pending["model"], **extra))
                        except Exception as e:
                            pending["card_error"] = str(e)
                    trace.data.update(status="waiting", pending=pending)
                    trace.save()
                    raise ctl.pause()

                if action == "hold":
                    event = trace.add(**{k: v for k, v in decision["event"].items() if k != "seq"})
                    stop_after(event)
                if action in ("replay", "release"):
                    old = {k: v for k, v in decision["event"].items() if k != "seq"}
                    result = decision.get("result", old["result"])
                    if decision.get("revise"):
                        old.update(result=result, **decision["revise"])
                    if action == "release":
                        old.update(status="ok", result=result,
                                   confirm=old.get("confirm", []) + decision.get("confirm", []))
                    trace.add(**old)
                    engine.store(record, result)
                    continue
                if action == "result":
                    bad = check_format(fmt, decision["result"]) if fmt and check_format else []
                    if bad:
                        raise DSLError(f"第 {n} 行：外部交的结果不符合格式 {fmt[0]}：" + "；".join(bad[:5]))
                    trace.add(type="task", **request, started=_stamp(), status="ok", source="external",
                              model="external", seconds=0.0, result=decision["result"],
                              actor=decision.get("actor", "workflow_ctl"), **metadata)
                    engine.store(record, decision["result"])
                    continue
                use_role = decision.get("role") or role
                use_model = decision.get("model")
                if action == "wait":
                    stop(use_role, use_model)
                if action != "run":
                    raise DSLError(f"第 {n} 行：外部控制给了未知动作：{action}")
                t0, started = time.time(), _stamp()
                event = dict(type="task", **request, started=started, **metadata)
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
                review = ctl is not None and decision.get("after", False)
                review_meta = {"notes": decision.get("notes", []), "confirm": decision.get("confirm", [])} if review else {}
                trace.update(ev, **getattr(engine, "_wf_last_call", {}), status="review" if review else "ok",
                             result=result, seconds=round(time.time() - t0, 1), **review_meta)
                if review:
                    stop_after(ev)
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
