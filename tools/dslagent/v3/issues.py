"""核查.zs / 修改.zs 用：问题清单的存 / 读 plan/issues/<序号>.md（序号分配、渲染、解析），程序检查条目（program_items），
疑点检查（run_logic_checks，角色 logic_check，按约定内容 hash 缓存；现在没有动词调它）。各路结果怎么合并见 audit.merge；
调模型找问题的部分写在 核查.zs 里（派任务）。

问题清单格式（模型出参 + 程序检查问题 一起序号）：

    # 问题清单 <序号>

    1. 问题描述……
       涉及模块：graph、vocab
       依据：需求第 3 节 / plan/top.zs 模块 vocab 说明 / 程序检查

每条用「N. 」开头，后面跟缩进的「涉及模块：」「依据：」两行（都可省，是给人看的展示文字，不是键名）。
issue 含换行时，第 2 行起每行前加 6 个空格（续行），解析时并回 issue；续行即使以「1. 」开头也不算新条目。
parse_issues() 解一份清单文本回列表，条目字段名是 issue/modules/basis（format_issue 兼容旧键 问题/涉及模块/依据）。
"""
import hashlib
import json
import re
from pathlib import Path

from . import globalcheck as GC


def issues_dir(project):
    return Path(project) / "plan" / "issues"


def next_no(project):
    d = issues_dir(project)
    have = [int(f.stem) for f in d.glob("*.md") if f.stem.isdigit()] if d.is_dir() else []
    return max(have, default=0) + 1


def latest_path(project):
    d = issues_dir(project)
    have = sorted((f for f in (d.glob("*.md") if d.is_dir() else []) if f.stem.isdigit()), key=lambda f: int(f.stem))
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
    try:
        p.resolve().relative_to(Path(project).resolve())
    except ValueError:
        raise ValueError(f"问题清单「{ref}」不在项目目录里") from None
    return p


CONT = " " * 6   # 多行 issue 的续行缩进（比「涉及模块：」「依据：」的 3 格缩进深，解析时靠它区分）


def format_issue(i, item):
    issue = str(item.get("issue", item.get("问题", "")) or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    first, *rest = issue.split("\n")
    lines = [f"{i}. {first}"] + [CONT + r for r in rest]
    mods = item.get("modules", item.get("涉及模块"))
    if mods:
        mods = mods if isinstance(mods, str) else "、".join(mods)
        lines.append(f"   涉及模块：{' '.join(mods.split())}")
    basis = item.get("basis", item.get("依据"))
    if basis:
        lines.append(f"   依据：{' '.join(str(basis).split())}")
    return "\n".join(lines)


def render(no, items):
    body = "\n".join(format_issue(i, it) for i, it in enumerate(items, 1))
    return f"# 问题清单 {no}\n\n" + (body + "\n" if body else "（没有发现问题）\n")


ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def parse_issues(text):
    """问题清单文本 → [{"issue", "modules", "basis"}, …]（顺序即原序号）。"""
    items = []
    cur = None
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        if cur is not None and raw.startswith(CONT):      # 多行 issue 的续行（即使以「1. 」开头也不是新条目）
            cur["issue"] += "\n" + raw[len(CONT):]
            continue
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
    for it in items:
        it["issue"] = it["issue"].rstrip()
    return items


def program_items(project, top):
    """程序检查（全局检查 + 依赖与顶层不一致）→ 问题清单条目列表（并入核查结果，basis 统一写「程序检查」）。"""
    g = GC.full_check(project, top)
    items = []
    for m, probs in sorted(g["按模块"].items()):
        for p in probs:
            items.append({"issue": p, "modules": m, "basis": "程序检查"})
    return items


def logic_cache_path(ctx):
    return ctx.out / "logic_cache.json"


def run_logic_checks(ctx, top, backend=None):
    """对 top 里全部已有约定的模块并行跑角色 logic_check（找伪代码逻辑漏洞），按约定内容 hash 缓存——内容没变
    不重调模型。疑点转成问题清单条目（依据写「logic_check(疑点)」，由修改规划决定采不采纳），不单独存盘，
    并入最终问题清单。"""
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
