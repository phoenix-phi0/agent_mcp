"""顶层规划 / 约定规划的「写、检查、存」（verbs/v3 的 写规划 / 检查规划 / 存规划 / 已有规划 是它们的壳）。

写：提示词 = prompts/<种类>.md（system），user = 需求 + 顶层规划 + 上游已通过的约定（+ 重写时上次的文本和问题）；调模型走 v2 的 Model（计数、记账）。
种类用中文名：顶层（产物 plan/top.zs）、约定（产物 contracts/<模块>.md）。
"""
import re
from pathlib import Path

from tools.dsl_core import ScriptHalt

from tools import ui_actions as UIA

from .. import guard as G
from .. import iftpl
from .. import v2 as V2
from ..packs.dslproj import contract as DC
from . import catalog as CAT
from . import contracts as VC
from . import top as VT
from .core import prompt_text, syntax_text

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
    if kind == "约定":
        CAT.refresh(ctx.project)
    return rel_of(kind, module)


def without_cases(text):
    """约定全文去掉「## 用例」小节（上游约定给下游看时用，用例对下游没用）。"""
    out, skip = [], False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("##"):
            skip = line.strip().lstrip("#").strip() == "用例"
        if not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def syntax_part(ctx):
    """种类=约定 的写 / 复核材料里附的项目写法说明（与 run_entry 注入的 syntax 同一份）；没有就不带。"""
    syntax = syntax_text(ctx).strip()
    if not syntax:
        return []
    return ["【项目写法说明（与核查用的同一份）】\n" + syntax
            + "\n\n约定里写的接口、认证、表、查询都必须是附上的项目写法说明里支持的写法。"]


def user_text(ctx, kind, req, module="", problems="", prev=""):
    parts = [f"【需求】\n{(req or '').strip()}"]
    ui = UIA.summary(ctx.project)
    if ui:
        rule = ("分模块时给每个远程动作一个归属：拥有它的模块要为它出公开函数和接口（接口行带「动作 <名>」）。"
                if kind == "顶层" else
                "本模块拥有的动作都要在「## 接口」里有且只有一个接口声明「动作 <名>」（方法 POST）。"
                "接口返回封装用【接口封装模板】清单里的模板写：接口行在「动作」后写「模板 <中文名> 键=值 …」，"
                "只能用清单里的模板、参数照清单（键=值 之间不能有空格）；页面要的信封清单里没有模板能表达时，"
                "不要自创封装写法——接口先不加模板（照旧返回裸对象），复核会把这类缺口当问题报出来。")
        parts.append("【前端页面 ui/*.ui 的远程动作（程序提取，只读；前端只会发 POST {action, form}，"
                     "接口直接返回页面要的信封 messages/state/lists/form/go）】\n" + ui + "\n\n" + rule)
        if kind == "约定":
            parts.append("【接口封装模板（程序从模板库 tools/dslagent/templates/iface/ 生成，返回封装只能从这里选）】\n"
                         + iftpl.listing())
    if kind == "顶层":
        cat = CAT.path_of(ctx.project)
        if cat.is_file():
            parts.append("【项目接口目录 plan/catalog.md（只读参考，程序生成：已有约定的各模块说明 / 依赖 / 表 / 公开函数 / 接口）】\n"
                          + cat.read_text(encoding="utf-8").strip())
    if kind == "约定":
        top = current_top(ctx)
        mine = next(m for m in top["模块"] if m["名"] == module)
        top_text = ctx.top_path().read_text(encoding="utf-8").strip()
        parts.extend(syntax_part(ctx))
        parts.append(f"【顶层规划 plan/top.zs】\n{top_text}")
        parts.append(f"【本次要写的模块】\n模块 {module}\n依赖 {' '.join(mine['依赖']) or '无'}")
        if mine.get("提供"):
            parts.append("【本模块必须提供的公开函数（top.zs 里「提供」写的，别的模块要调用；约定里每个都必须有，且写成「公开 函数」，函数名一字不差）】\n"
                         + "\n".join(f"- {f}" for f in mine["提供"]))
        ups = []
        for d in mine["依赖"]:
            f = VC.path_of(ctx.project, d)
            if f.is_file():
                ups.append(f"### 上游模块 {d}（直接依赖，可以调用）\n```\n{without_cases(f.read_text(encoding='utf-8')).strip()}\n```")
        provided = [f"- 模块 {d} 提供：{' '.join(m['提供'])}" for d in mine["依赖"] for m in top["模块"] if m["名"] == d and m.get("提供")]
        parts.append("【上游模块的约定（已通过检查并冻结，不能改；跨模块只能调上游约定里写了「公开」的函数，上游提供的见顶层「提供」）】\n"
                     + ("\n".join(provided) + "\n\n" if provided else "") + ("\n\n".join(ups) if ups else "（本模块没有依赖）"))
        brief = CAT.brief_index(ctx.project, top_text, exclude={module, *mine["依赖"]})
        parts.append("【项目接口目录：除上面直接依赖外，其它已有约定的模块一行概要（只读参考，不能直接调用；"
                      "需要调用就把它加进「依赖」，之后会给到它的约定全文）】\n" + (brief or "（没有别的模块）"))
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
        prev = ctx.last_text.get(key) or existing(ctx, kind, module)       # 续跑时上一轮不是本进程写的：拿盘上不过检查的那份当"上次的内容"
    user = user_text(ctx, kind, req or ctx.req, module, problems, prev)
    tag = "v3_top" if kind == "顶层" else f"v3_contract_{re.sub(r'[^A-Za-z0-9_]', '_', module)}"
    try:
        text = ctx.M(prompt_text(PROMPT_OF[kind]), user, tag, model,
                     limits=G.contract_limits() if kind == "约定" else None)
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


REVIEW_FAIL = "未复核"


def parse_review(text):
    """复核回复 → {passed: bool, issues: [str]}；不是 JSON 或缺字段返回 None。兼容旧键 通过/问题列表/问题。"""
    import json
    t = (text or "").strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        j = json.loads(t[a:b + 1])
    except ValueError:
        return None
    if not isinstance(j, dict) or not ({"passed", "通过"} & set(j)):
        return None
    raw = j["passed"] if "passed" in j else j.get("通过")
    ok = raw is True or str(raw).strip() in ("是", "true", "True", "1", "通过")
    items = j.get("issues") if "issues" in j else (j.get("问题列表") or j.get("问题") or [])
    if isinstance(items, str):
        items = [items]
    items = [str(x).strip() for x in items if str(x).strip()]
    if not ok and not items:
        return None
    return {"passed": ok, "issues": items}


def review_user(ctx, module, text, req):
    """复核入参 = 需求全文 + top.zs（如果有）+ 项目接口目录（如果有，按它判断「分给别的模块的不算缺失」）+ 本约定。"""
    parts = [f"【本轮需求全文】\n{(req or '').strip()}"]
    if ctx.top_path().is_file():
        parts.append(f"【顶层规划 plan/top.zs】\n{ctx.top_path().read_text(encoding='utf-8').strip()}")
    cat = CAT.path_of(ctx.project)
    if cat.is_file():
        parts.append("【项目接口目录 plan/catalog.md（只读参考：按 top.zs 的分工判断——需求里的事如果已经在别的模块的"
                      "公开函数 / 接口里找得到，不算本模块缺失；反过来同一件事被两个模块各做一份，在问题里指出）】\n"
                      + cat.read_text(encoding="utf-8").strip())
    parts.append("【接口封装模板（程序从模板库生成；约定里的接口返回封装只能用这些模板，写法「模板 <中文名> 键=值 …」）】\n"
                 + iftpl.listing())
    parts.extend(syntax_part(ctx))
    parts.append(f"【模块 {module} 的约定】\n{VT.clean(text).strip()}")
    return "\n\n".join(parts)


def review(ctx, module, text, req="", model="sonnet"):
    """约定通过程序检查后，调一次模型对照需求复核 → {passed, issues, 状态}（状态 = 已复核 / 未复核；未复核时 passed=False）。
    回复不是约定的 JSON 时再问一次；还不行就返回 passed=False、状态=未复核（带一条说明问题）——没复核不算通过，
    由 规划一份.zs 带原因重写、次数用尽 终止 失败。预算 / 花费 / 墙钟用完抛 ScriptHalt。"""
    if not str(module or "").strip():
        raise ValueError("复核约定要写模块名")
    user = review_user(ctx, module, text, req or ctx.req)
    tag = f"v3_review_{re.sub(r'[^A-Za-z0-9_]', '_', module)}"
    got = None
    for _ in range(2):
        ctx.guard()
        ctx.take_call()
        try:
            raw = ctx.M(prompt_text("review.md"), user, tag, model, limits=G.contract_limits())
        except V2.Stop as e:
            raise ScriptHalt("超出预期", str(e), "") from None
        except RuntimeError as e:
            ctx.log("规划", 种类="约定", 模块=module, 事件="复核", 状态=REVIEW_FAIL, 原因=f"模型没有回应：{str(e)[:200]}")
            continue
        got = parse_review(raw)
        if got is not None:
            break
    if got is None:
        ctx.log("规划", 种类="约定", 模块=module, 事件="复核", 状态=REVIEW_FAIL, 原因="回复不是 {passed, issues} 的 JSON")
        return {"passed": False, "issues": [f"复核没做成（模型没有给出合格回复，不是约定本身的问题）：请原样保留约定要点重新提交以便再复核"],
                "状态": REVIEW_FAIL}
    ok = got["passed"] and not got["issues"]
    probs = [f"复核（对照需求）：{p}" for p in got["issues"]]
    ctx.log("规划", 种类="约定", 模块=module, 事件="复核", 状态="已复核", 通过=ok, 条数=len(probs), 问题=got["issues"])
    return {"passed": ok, "issues": probs, "状态": "已复核"}
