"""核查.zs 用：调模型找全局性问题（职责重复、模块间缺口、跨模块调用对不上、偏离需求、伪代码留白没写死），
与程序检查结果并成一份问题清单，存 / 读 plan/issues/<序号>.md。确定性部分（序号分配、文件读写、hash 缓存）在这里；
调模型的部分复用 ctx.M（跟 planning.write 一样走 v2 的 Model，记账 / 预算）。

问题清单格式（模型出参 + 程序检查问题 一起序号）：

    # 问题清单 <序号>

    1. 问题描述……
       涉及模块：graph、vocab
       依据：需求第 3 节 / plan/top.zs 模块 vocab 说明 / 程序检查

每条用「N. 」开头，后面跟缩进的「涉及模块：」「依据：」两行（都可省，是给人看的展示文字，不是键名）。
parse_issues() 解一份清单文本回列表，条目字段名是 issue/modules/basis（模型出参与存盘前的内部表示一致；
兼容旧键 问题/涉及模块/依据，见 parse_model_issues）。
"""
import hashlib
import json
import re
from pathlib import Path

from tools.dsl_core import ScriptHalt

from .. import v2 as V2
from . import globalcheck as GC
from . import top as VT
from .core import prompt_text


def issues_dir(project):
    return Path(project) / "plan" / "issues"


def next_no(project):
    d = issues_dir(project)
    have = [int(f.stem) for f in d.glob("*.md")] if d.is_dir() else []
    return max(have, default=0) + 1


def latest_path(project):
    d = issues_dir(project)
    have = sorted((d.glob("*.md") if d.is_dir() else []), key=lambda f: int(f.stem))
    return have[-1] if have else None


def resolve(project, ref):
    """「问题」入参（路径 或 "最新"/"latest"）→ Path；找不到抛 ValueError。"""
    ref = (ref or "").strip()
    if not ref or ref in ("最新", "latest"):
        p = latest_path(project)
        if p is None:
            raise ValueError("plan/issues/ 下还没有问题清单")
        return p
    p = Path(project) / ref if not Path(ref).is_absolute() else Path(ref)
    if not p.is_file():
        raise ValueError(f"问题清单「{ref}」不存在")
    return p


def format_issue(i, item):
    lines = [f"{i}. {item.get('issue', item.get('问题', ''))}"]
    mods = item.get("modules", item.get("涉及模块"))
    if mods:
        mods = mods if isinstance(mods, str) else "、".join(mods)
        lines.append(f"   涉及模块：{mods}")
    basis = item.get("basis", item.get("依据"))
    if basis:
        lines.append(f"   依据：{basis}")
    return "\n".join(lines)


def render(no, items):
    body = "\n".join(format_issue(i, it) for i, it in enumerate(items, 1))
    return f"# 问题清单 {no}\n\n" + (body + "\n" if body else "（没有发现问题）\n")


ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def parse_issues(text):
    """问题清单文本 → [{"issue", "modules", "basis"}, …]（顺序即原序号）。"""
    out = None
    items = []
    cur = None
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        m = ITEM_RE.match(raw.strip())
        if m:
            if cur:
                items.append(cur)
            cur = {"issue": m.group(2).strip(), "modules": "", "basis": ""}
            continue
        s = raw.strip()
        if cur and s.startswith("涉及模块："):
            cur["modules"] = s[len("涉及模块："):].strip()
        elif cur and s.startswith("依据："):
            cur["basis"] = s[len("依据："):].strip()
    if cur:
        items.append(cur)
    return items


def parse_model_issues(raw):
    """模型出参：JSON 数组，每项 {"issue", "modules"(可选 list|str), "basis"(可选)}；兼容旧键 问题/涉及模块/依据。
    不是 JSON / 不是数组 → []。"""
    t = (raw or "").strip()
    a, b = t.find("["), t.rfind("]")
    if a < 0 or b <= a:
        return []
    try:
        j = json.loads(t[a:b + 1])
    except ValueError:
        return []
    if not isinstance(j, list):
        return []
    out = []
    for it in j:
        if not isinstance(it, dict):
            continue
        issue = str(it.get("issue") or it.get("问题") or "").strip()
        if issue:
            out.append({"issue": issue, "modules": it.get("modules") or it.get("涉及模块") or "",
                        "basis": it.get("basis") or it.get("依据") or ""})
    return out


def program_items(project, top):
    """程序检查（全局检查 + 依赖与顶层不一致）→ 问题清单条目列表（并入核查结果，basis 统一写「程序检查」）。"""
    g = GC.full_check(project, top)
    items = []
    for m, probs in sorted(g["按模块"].items()):
        for p in probs:
            items.append({"issue": p, "modules": m, "basis": "程序检查"})
    return items


def cache_key(req_text, task, top_text, catalog_text, program, prev_plan):
    h = hashlib.sha256()
    for part in (req_text, task or "", top_text, catalog_text or "", json.dumps(program, ensure_ascii=False, sort_keys=True), prev_plan or ""):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def cache_path(ctx):
    return ctx.out / "audit_cache.json"


def user_text(req_text, task, top_text, catalog_text, program, prev_plan):
    parts = [f"【需求】\n{(req_text or '').strip()}"]
    if (task or "").strip():
        parts.append(f"【任务】\n{task.strip()}\n（有任务时，问题清单要列出「完成这个任务要改的地方」，不只是找现有偏差）")
    parts.append(f"【顶层规划 plan/top.zs】\n{(top_text or '').strip() or '（还没有）'}")
    if (catalog_text or "").strip():
        parts.append(f"【项目接口目录 plan/catalog.md】\n{catalog_text.strip()}")
    brief = "；".join(f"{m}：{'; '.join(v)}" for m, v in sorted(program.get("按模块", {}).items())) or "（没有发现问题）"
    parts.append(f"【程序检查结果（已经确定的问题，直接并入你的问题清单，不用重新判断）】\n{brief}")
    if (prev_plan or "").strip():
        parts.append(f"【上一份修改计划原文】\n{prev_plan.strip()}")
    return "\n\n".join(parts)


def logic_cache_path(ctx):
    return ctx.out / "logic_cache.json"


def run_logic_checks(ctx, top, backend=None):
    """对 top 里全部已有约定的模块并行跑角色 logic_check（找伪代码逻辑漏洞），按约定内容 hash 缓存——内容没变
    不重调模型。疑点转成问题清单条目（依据写「logic_check(疑点)」，由修改规划决定采不采纳），不单独存盘，
    并入 run_audit 的最终问题清单。"""
    from .. import roles as R
    from . import contracts as VC
    cache_f = logic_cache_path(ctx)
    try:
        cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.is_file() else {}
    except ValueError:
        cache = {}
    mods = [m["名"] for m in top.get("模块", [])]
    texts, todo = {}, {}
    for m in mods:
        p = VC.path_of(ctx.project, m)
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        texts[m] = text
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if cache.get(m, {}).get("hash") != h:
            todo[m] = h
    items_out, total_cost = [], 0.0
    if todo:
        def backend_(spec, system, user, timeout):
            if backend is not None:
                return backend(spec, system, user, timeout)
            if ctx.M.real:
                from .. import engines as EG
                return EG.call(spec, system, user, timeout)
            return ctx.M.backend(system, user, "v3_logic_check", timeout, model=spec["spec"])

        import concurrent.futures as CF
        with CF.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(R.dispatch_agent, "logic_check", "", {"约定": texts[m]}, "json",
                               out_dir=ctx.out, backend=backend_, parent_id=str(ctx.out)): m for m in todo}
            for fut in CF.as_completed(futs):
                m = futs[fut]
                r = fut.result()
                total_cost += r.get("cost") or 0.0
                found = []
                if r["status"] == "ok":
                    try:
                        found = json.loads(r["result"])
                    except ValueError:
                        found = []
                cache[m] = {"hash": todo[m], "items": [
                    {"issue": it.get("issue") or it.get("问题") or "", "modules": m,
                     "basis": f"logic_check(疑点)：{it.get('basis') or it.get('依据') or ''}"}
                    for it in found if isinstance(it, dict) and (it.get("issue") or it.get("问题"))]}
        cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in mods:
        if m in cache:
            items_out.extend(cache[m].get("items", []))
    if total_cost:
        with ctx.lock:
            ctx.module_cost += total_cost
    return items_out


def run_audit(ctx, task="", model="sonnet", logic_check=False):
    """核查：程序检查 + 调模型找问题 → (items, count)。按输入 hash 缓存——hash 没变直接用缓存，不重调模型。"""
    project = ctx.project
    top_text = ctx.top_path().read_text(encoding="utf-8") if ctx.top_path().is_file() else ""
    from . import catalog as CAT
    cat_f = CAT.path_of(project)
    catalog_text = cat_f.read_text(encoding="utf-8") if cat_f.is_file() else ""
    try:
        top = VT.load(top_text) if top_text else {"模块": []}
    except ValueError:
        top = {"模块": []}
    prog_items = program_items(project, top) if top_text else []
    program = GC.full_check(project, top) if top_text else {"条数": 0, "按模块": {}, "摘要": ""}

    from . import change_plan as CP
    prev_plan = ""
    last = CP.latest_plan_path(project)
    if last is not None:
        prev_plan = last.read_text(encoding="utf-8")

    key = cache_key(ctx.req, task, top_text, catalog_text, program, prev_plan)
    cache = {}
    cf = cache_path(ctx)
    if cf.is_file():
        try:
            cache = json.loads(cf.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
    if cache.get("key") == key and isinstance(cache.get("model_items"), list):
        model_items = cache["model_items"]
        ctx.log("核查", 事件="命中缓存", key=key[:12])
    else:
        ctx.guard()
        ctx.take_call()
        user = user_text(ctx.req, task, top_text, catalog_text, program, prev_plan)
        try:
            raw = ctx.M(prompt_text("audit.md"), user, "v3_audit", model or "sonnet")
        except V2.Stop as e:
            raise ScriptHalt("超出预期", str(e), "") from None
        except RuntimeError as e:
            ctx.log("核查", 事件="模型没有回应", 原因=str(e)[:200])
            raw = "[]"
        model_items = parse_model_issues(raw)
        cf.write_text(json.dumps({"key": key, "model_items": model_items}, ensure_ascii=False, indent=1), encoding="utf-8")
        ctx.log("核查", 事件="调模型", key=key[:12], 模型条数=len(model_items))
    logic_items = run_logic_checks(ctx, top) if logic_check and top_text else []
    items = prog_items + model_items + logic_items
    ctx.log("核查", 事件="汇总", 程序条数=len(prog_items), 模型条数=len(model_items), 疑点条数=len(logic_items), 总数=len(items))
    return items


def save(project, items):
    no = next_no(project)
    d = issues_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    text = render(no, items)
    p = d / f"{no}.md"
    p.write_text(text, encoding="utf-8", newline="\n")
    return str(p.relative_to(Path(project)))


def load(project, ref):
    p = resolve(project, ref)
    return parse_issues(p.read_text(encoding="utf-8")), str(p.relative_to(Path(project)))
