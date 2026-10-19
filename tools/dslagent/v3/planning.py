"""顶层规划 / 约定规划的「写、检查、存」（verbs/v3 的 写规划 / 检查规划 / 存规划 / 已有规划 是它们的壳）。

写：提示词 = prompts/<种类>.md（system），user = 需求 + 顶层规划 + 上游已通过的约定（+ 重写时上次的文本和问题）；调模型走 v2 的 Model（计数、记账）。
种类用中文名：顶层（产物 plan/top.zs）、约定（产物 contracts/<模块>.md）。
"""
import re
from pathlib import Path

from tools.dsl_core import ScriptHalt

from .. import v2 as V2
from ..packs.dslproj import contract as DC
from . import contracts as VC
from . import top as VT
from .core import prompt_text

KINDS = ("顶层", "约定")
PROMPT_OF = {"顶层": "top.md", "约定": "contract.md"}


def need_kind(kind, module=""):
    if kind not in KINDS:
        raise ValueError(f"规划种类只有 {' / '.join(KINDS)}，收到「{kind}」")
    if kind == "约定" and not str(module or "").strip():
        raise ValueError("种类=约定 要写模块名")
    return kind


def file_of(ctx, kind, module=""):
    return ctx.top_path() if kind == "顶层" else VC.path_of(ctx.project, module)


def rel_of(kind, module=""):
    return "plan/top.zs" if kind == "顶层" else f"contracts/{module}.md"


def existing(ctx, kind, module=""):
    f = file_of(ctx, need_kind(kind, module), module)
    return f.read_text(encoding="utf-8") if f.is_file() else ""


def current_top(ctx):
    """已存的 plan/top.zs → top；没有或不过检查抛 ValueError。"""
    t = ctx.top_path()
    if not t.is_file():
        raise ValueError("还没有 plan/top.zs（先做顶层规划）")
    return VT.load(t.read_text(encoding="utf-8"))


def check(ctx, kind, text, module=""):
    """→ 问题列表（空 = 通过）。"""
    need_kind(kind, module)
    if not (text or "").strip():
        return ["回复是空的（模型没有给出内容）"]
    text = VT.clean(text)
    if kind == "顶层":
        return VT.check(text)
    try:
        top = current_top(ctx)
    except ValueError as e:
        return [str(e)]
    return VC.check(text, module, top, ctx.project)


def save(ctx, kind, text, module=""):
    f = file_of(ctx, need_kind(kind, module), module)
    f.parent.mkdir(parents=True, exist_ok=True)
    body = VT.clean(text) if kind == "顶层" else DC.normalize(VT.clean(text))
    f.write_text(body, encoding="utf-8", newline="\n")
    return rel_of(kind, module)


def ancestors(top, module):
    """module 的全部上游（依赖的依赖…），上游在前。"""
    deps = {m["名"]: m["依赖"] for m in top["模块"]}
    order, seen = [], set()

    def visit(n):
        for d in deps.get(n, []):
            if d not in seen:
                seen.add(d)
                visit(d)
                order.append(d)
    visit(module)
    return order


def without_cases(text):
    """约定全文去掉「## 用例」小节（上游约定给下游看时用，用例对下游没用）。"""
    out, skip = [], False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("##"):
            skip = line.strip().lstrip("#").strip() == "用例"
        if not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def user_text(ctx, kind, req, module="", problems="", prev=""):
    parts = [f"【需求】\n{(req or '').strip()}"]
    if kind == "约定":
        top = current_top(ctx)
        mine = next(m for m in top["模块"] if m["名"] == module)
        parts.append(f"【顶层规划 plan/top.zs】\n{ctx.top_path().read_text(encoding='utf-8').strip()}")
        parts.append(f"【本次要写的模块】\n模块 {module}\n依赖 {' '.join(mine['依赖']) or '无'}")
        ups = []
        for u in ancestors(top, module):
            f = VC.path_of(ctx.project, u)
            if f.is_file():
                ups.append(f"### 上游模块 {u}" + ("（直接依赖，可以调用）" if u in mine["依赖"] else "（间接上游，只能当数据来源，不能直接调用）")
                           + f"\n```\n{without_cases(f.read_text(encoding='utf-8')).strip()}\n```")
        parts.append("【上游模块的约定（已通过检查并冻结，不能改；只能调用其中的公开函数）】\n" + ("\n\n".join(ups) if ups else "（本模块没有依赖）"))
    if problems.strip():
        parts.append(f"【你上次写的内容】\n{prev.strip()}\n\n【检查发现的问题（逐条改掉，其余保持）】\n{problems.strip()}")
    return "\n\n".join(parts)


def write(ctx, kind, req="", module="", problems="", model="sonnet"):
    """调一次模型写 → 文本（模型没有回应时是空串，由检查报出来）。预算 / 花费 / 墙钟用完抛 ScriptHalt。"""
    need_kind(kind, module)
    key = (kind, module)
    ctx.guard()
    ctx.take_call()
    with ctx.lock:
        ctx.attempts[key] = n = ctx.attempts.get(key, 0) + 1
        prev = ctx.last_text.get(key, "")
    user = user_text(ctx, kind, req or ctx.req, module, problems, prev)
    tag = "v3_top" if kind == "顶层" else f"v3_contract_{re.sub(r'[^A-Za-z0-9_]', '_', module)}"
    try:
        text = ctx.M(prompt_text(PROMPT_OF[kind]), user, tag, model)
    except V2.Stop as e:
        raise ScriptHalt("超出预期", str(e), "") from None
    except RuntimeError as e:
        ctx.log("规划", 种类=kind, 模块=module, 次=n, 事件="模型没有回应", 原因=str(e)[:200])
        return ""
    text = VT.clean(text)
    with ctx.lock:
        ctx.last_text[key] = text
    (ctx.out / "steps").mkdir(exist_ok=True)
    (ctx.out / "steps" / f"{'top' if kind == '顶层' else 'contract_' + module}_w{n}.txt").write_text(text, encoding="utf-8")
    return text


def tasks(group, req, tries, model):
    """一层的模块（逗号分隔）→ 并行执行用的任务列表（每个模块一项，脚本 = 规划一份）。"""
    names = [x for x in re.split(r"[,，\s]+", group or "") if x]
    return [{"脚本": "规划一份", "参数": {"种类": "约定", "模块": n, "需求": req, "最多": str(tries), "模型": model}} for n in names]
