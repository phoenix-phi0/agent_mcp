"""修改.zs 用：写修改计划（调模型）+ 检查修改计划（程序）+ 存 plan/changes/<序号>.zs。
计划四种动词的执行（改需求 改 plan/req.md 对应节 + 追加变更记录、新增模块/删除模块 改 top.zs、改约定 带条目重写约定）
本次预算未实现，留给后续任务（见 data/reports/rebuild_D.md「没做完的部分」）。

计划动词（产出约定）：
    改需求 <节号> <新内容或改法>
    新增模块 <名> 依赖=<…> 说明=<…>
    删除模块 <名>
    改约定 <模块> <改动条目>
每行可带「# 对应问题 N」。

check_plan(text, issues, top) -> 问题列表（空 = 通过）：
- 格式：每行必须是四种动词之一开头（parse_plan 已经按行拆出格式问题）
- 模块存在：删除模块 / 改约定 的模块名要在 top.zs 里；新增模块 不能和已有模块重名
- 不成环：新增模块 的「依赖=」只能是 top.zs 里的模块或本次计划里别的「新增模块」，且合起来不成环
- 新增模块写了说明：「新增模块 …」必须带「说明=」
- 每个问题被覆盖：issues 里的编号都在至少一行「# 对应问题」里出现过
- 改需求的节号存在：「改需求 <节号> …」的节号要能在需求文本的「## <节号>」或「<节号>.」标题里找到（找不到需求文本时跳过这项）
"""
import re
from pathlib import Path

from tools.dsl_core import ScriptHalt

from .. import v2 as V2
from .core import prompt_text


def changes_dir(project):
    return Path(project) / "plan" / "changes"


def next_no(project):
    d = changes_dir(project)
    have = [int(f.stem) for f in d.glob("*.zs")] if d.is_dir() else []
    return max(have, default=0) + 1


def latest_plan_path(project):
    d = changes_dir(project)
    have = sorted((d.glob("*.zs") if d.is_dir() else []), key=lambda f: int(f.stem))
    return have[-1] if have else None


DIRECTIVE_RE = re.compile(r"^(改需求|新增模块|删除模块|改约定)\s")


def strip_comment_tag(line):
    """去掉行末「# 对应问题 N」，返回 (正文, 对应问题号|None)。"""
    m = re.search(r"#\s*对应问题\s*(\d+)\s*$", line)
    if not m:
        return line.rstrip(), None
    return line[:m.start()].rstrip(), int(m.group(1))


def parse_plan(text):
    """修改计划 .zs 文本 → ([{"动词", "内容", "对应问题"}], 问题列表)。只认四种动词开头的行，空行/注释行跳过。"""
    items, probs = [], []
    for no, raw in enumerate((text or "").replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, issue_no = strip_comment_tag(line)
        if not DIRECTIVE_RE.match(body):
            probs.append(f"第 {no} 行：只能用 改需求 / 新增模块 / 删除模块 / 改约定 开头，现在是「{body[:40]}」")
            continue
        verb, _, rest = body.partition(" ")
        items.append({"动词": verb, "内容": rest.strip(), "对应问题": issue_no, "行": no})
    return items, probs


def user_text(issues_text, req_excerpt, task, top_text, catalog_text, contracts_text):
    parts = [f"【问题清单】\n{issues_text.strip()}"]
    if (task or "").strip():
        parts.append(f"【任务】\n{task.strip()}")
    if (req_excerpt or "").strip():
        parts.append(f"【需求中被引用 / 任务涉及的章节】\n{req_excerpt.strip()}")
    parts.append(f"【顶层规划 plan/top.zs】\n{(top_text or '').strip() or '（还没有）'}")
    if (catalog_text or "").strip():
        parts.append(f"【项目接口目录 plan/catalog.md】\n{catalog_text.strip()}")
    if (contracts_text or "").strip():
        parts.append(f"【涉及模块的约定（去掉用例）】\n{contracts_text.strip()}")
    return "\n\n".join(parts)


def write(ctx, issues_text, task="", model="sonnet"):
    """调一次模型写修改计划文本（未必通过 parse_plan；检查留给 检查修改计划，本次预算未实现）。"""
    ctx.guard()
    ctx.take_call()
    top_text = ctx.top_path().read_text(encoding="utf-8") if ctx.top_path().is_file() else ""
    from . import catalog as CAT
    cat_f = CAT.path_of(ctx.project)
    catalog_text = cat_f.read_text(encoding="utf-8") if cat_f.is_file() else ""
    user = user_text(issues_text, ctx.req, task, top_text, catalog_text, "")
    try:
        text = ctx.M(prompt_text("change_plan.md"), user, "v3_change_plan", model or "sonnet")
    except V2.Stop as e:
        raise ScriptHalt("超出预期", str(e), "") from None
    except RuntimeError as e:
        ctx.log("修改计划", 事件="模型没有回应", 原因=str(e)[:200])
        text = ""
    return (text or "").strip() + "\n"


def save(project, text):
    no = next_no(project)
    d = changes_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{no}.zs"
    p.write_text(text, encoding="utf-8", newline="\n")
    return str(p.relative_to(Path(project)))


SECTION_RE = re.compile(r"^(?:##+\s*|)(\d+(?:\.\d+)*)[.\s]")


def req_sections(req_text):
    """需求文本里出现过的节号（「## 3」「3.2 」这类行首数字编号）集合。"""
    out = set()
    for raw in (req_text or "").replace("\r\n", "\n").split("\n"):
        m = SECTION_RE.match(raw.strip())
        if m:
            out.add(m.group(1))
    return out


def _new_mod_deps(items):
    deps = {}
    for it in items:
        if it["动词"] != "新增模块":
            continue
        name = it["内容"].split()[0] if it["内容"].split() else ""
        m = re.search(r"依赖=(\S*)", it["内容"])
        dep_str = m.group(1) if m else ""
        deps[name] = [d for d in re.split(r"[,，]", dep_str) if d and d != "无"]
    return deps


def check_plan(text, issues, top, req_text=""):
    """→ 问题列表（空 = 通过）。issues：问题清单条目列表（1 开始编号与原清单一致）；top：top.load 的结果。"""
    items, probs = parse_plan(text)
    if not items and not probs:
        probs.append("计划是空的，没有一行指令")
    mod_names = {m["名"] for m in top.get("模块", [])}
    new_mods = set()
    covered = set()
    for it in items:
        no = it["对应问题"]
        if no:
            covered.add(no)
        verb, content = it["动词"], it["内容"]
        if verb == "新增模块":
            name = content.split()[0] if content.split() else ""
            if not name:
                probs.append(f"第 {it['行']} 行：新增模块 要写模块名")
            elif name in mod_names or name in new_mods:
                probs.append(f"第 {it['行']} 行：新增模块「{name}」已经存在，不能重名")
            else:
                new_mods.add(name)
            if "说明=" not in content:
                probs.append(f"第 {it['行']} 行：新增模块「{name}」没写「说明=」")
        elif verb == "删除模块":
            name = content.strip()
            if name not in mod_names:
                probs.append(f"第 {it['行']} 行：删除模块「{name}」不在 plan/top.zs 里")
        elif verb == "改约定":
            name = content.split()[0] if content.split() else ""
            if name not in mod_names and name not in new_mods:
                probs.append(f"第 {it['行']} 行：改约定的模块「{name}」不在 plan/top.zs 里（也不是本计划新增的）")
        elif verb == "改需求":
            sec = content.split()[0] if content.split() else ""
            secs = req_sections(req_text)
            if req_text and secs and sec not in secs:
                probs.append(f"第 {it['行']} 行：改需求的节号「{sec}」在需求文本里找不到")
    deps = _new_mod_deps(items)
    all_names = mod_names | new_mods
    from . import top as VT
    for m in top.get("模块", []):
        deps.setdefault(m["名"], m["依赖"])
    for name, ds in deps.items():
        for d in ds:
            if d not in all_names:
                probs.append(f"新增模块「{name}」依赖的「{d}」不是已有模块也不是本计划新增的模块")
    cyc = VT.find_cycle(deps)
    if cyc:
        probs.append("计划里的模块依赖成环：" + " → ".join(cyc))
    want = {i + 1 for i in range(len(issues))}
    missing = sorted(want - covered)
    if missing:
        probs.append("问题清单里这些编号没有被任何一行计划覆盖（# 对应问题 N）：" + "、".join(str(x) for x in missing))
    return probs
