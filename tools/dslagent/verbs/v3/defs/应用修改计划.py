"""应用修改计划：读一份修改计划（文本，或 plan/changes/<序号>.zs 的相对路径），按 change_plan.parse_plan 拆出四种
指令，直接执行其中不需要调模型的部分：
- 改需求：只在需求文件文末「变更记录」追加一行（节内容本身不动，按 change_plan.md 的约定：「改需求只改对应节号
  文末追加变更记录，不要整节重写」）；要求 ctx.req_path 已知，没有就 终止 失败。
- 新增模块 / 删除模块：改 plan/top.zs；删除连同文件与 state，复用 清理删掉的模块。
改约定、以及新增模块要写的约定本身不在这里调模型，留给调用方（执行修改计划.zs）按返回的「写约定目标」走
规划一份 的强制问题通道（新增=强制问题空走全流程含复核；改约定=强制问题带条目只跑程序检查）。
返回 {"改需求":[节号…], "新增模块":[名…], "删除模块":[名…], "改约定":[模块…], "写约定目标":{模块: 条目文本或空}}。
例如 设 r = 应用修改计划 {计划}
"""
import re
import sys
import time
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")

MOD_RE = re.compile(r"^模块\s+(\S+)")


def _code_part(line):
    i = line.find("#")
    while i >= 0:
        if i == 0 or line[i - 1] in " \t":
            return line[:i]
        i = line.find("#", i + 1)
    return line


def _plan_text(project, 计划):
    p = Path(计划)
    if not p.is_absolute():
        cand = project / p
        if cand.is_file():
            return cand.read_text(encoding="utf-8"), cand
    if p.is_file():
        return p.read_text(encoding="utf-8"), p
    return (计划 or ""), None


def _append_changelog(text, lines):
    body = (text or "").rstrip("\n")
    if "## 变更记录" not in body:
        body += "\n\n## 变更记录"
    return body + "\n" + "\n".join(lines) + "\n"


def _clean_removed_modules():
    import importlib.util
    p = Path(__file__).parent / "清理删掉的模块.py"
    spec = importlib.util.spec_from_file_location("_v3_apply_clean", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.清理删掉的模块()


def 应用修改计划(计划: str) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP, top as VT
    c = X.ctx()
    text, plan_path = _plan_text(c.project, 计划)
    items, probs = CP.parse_plan(text)
    if probs:
        X.fail("修改计划格式有问题，不能执行：" + "；".join(probs[:3]))
    plan_no = plan_path.stem if plan_path else ""

    req_secs, new_mods, del_mods, change_items = [], [], [], {}
    for it in items:
        verb, content = it["动词"], it["内容"]
        if verb == "改需求":
            sec, _, note = content.partition(" ")
            req_secs.append((sec.strip(), note.strip()))
        elif verb == "新增模块":
            name = content.split()[0] if content.split() else ""
            m = re.search(r"依赖=(\S*)", content)
            deps = [d for d in re.split(r"[,，]", m.group(1) if m else "") if d and d != "无"]
            new_mods.append((name, deps))
        elif verb == "删除模块":
            del_mods.append(content.strip())
        elif verb == "改约定":
            name, _, note = content.partition(" ")
            change_items.setdefault(name.strip(), []).append(note.strip())

    if req_secs:
        req_path = getattr(c, "req_path", None)
        if not req_path:
            X.fail("修改计划里有「改需求」，但没有需求文件路径（ctx.req_path 没设置）")
        rp = Path(req_path)
        old = rp.read_text(encoding="utf-8") if rp.is_file() else ""
        date = time.strftime("%Y-%m-%d")
        log_lines = [f"- {date} 计划 {plan_no}：改第 {sec} 节 — {note}" for sec, note in req_secs]
        rp.write_text(_append_changelog(old, log_lines), encoding="utf-8", newline="\n")
        c.log("修改计划", 事件="改需求", 节=[s for s, _ in req_secs], 路径=str(rp))

    del_set = {x for x in del_mods if x}
    if new_mods or del_set:
        if not c.top_path().is_file():
            X.fail("修改计划有新增/删除模块，但还没有 plan/top.zs")
        lines = VT.clean(c.top_path().read_text(encoding="utf-8")).splitlines()
        if del_set:
            kept = []
            for l in lines:
                mo = MOD_RE.match(_code_part(l).strip())
                if mo and mo.group(1) in del_set:
                    continue
                kept.append(l)
            lines = kept
        for name, deps in new_mods:
            dep_part = (" 依赖 " + " ".join(deps)) if deps else ""
            lines.append(f"模块 {name}{dep_part}")
        new_text = "\n".join(lines) + "\n"
        new_probs = VT.check(new_text)
        if new_probs:
            X.fail("执行新增/删除模块后 plan/top.zs 没通过检查：" + "；".join(new_probs[:3]))
        c.top_path().write_text(new_text, encoding="utf-8", newline="\n")
        c.log("修改计划", 事件="改顶层", 新增=[n for n, _ in new_mods], 删除=sorted(del_set))

    if del_set:
        _clean_removed_modules()

    targets = {name: "" for name, _ in new_mods}
    for name, notes in change_items.items():
        targets[name] = "\n".join(f"- {n}" for n in notes if n)

    return {
        "改需求": [s for s, _ in req_secs],
        "新增模块": [n for n, _ in new_mods],
        "删除模块": sorted(del_set),
        "改约定": sorted(change_items),
        "写约定目标": targets,
    }
