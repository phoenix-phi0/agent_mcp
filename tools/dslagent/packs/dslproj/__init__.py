"""资料包 dslproj：做 DSL 项目里的一个模块（entities / queries / services / routes）。接口见 packs/__init__.py，写法说明见 packs/README.md。

任务：含一行「模块 <名>」；项目里有 contracts/<名>.md（约定：表、函数头 + 伪代码、接口、验收用例，格式见 contract.py）。
- 资料 materials：本模块约定全文、上游模块公开函数头、本模块现有文件（骨架）、DSL 项目写法速查（prompts/syntax.md）。
- 动词：code 包的读 / 搜 / 改 / 写 / 删文件 + dslproj 包的 加载检查 / 比对约定 / 跑用例（verbs/dslproj/）。
- 验收 accept：加载检查无错 + 比对约定一致 + 本模块用例全过（cases.py，空库、固定时间）；有问题派 1 次补改（edits），补改后再验一次。
- 范围 scope_for：entities/<模块>.entity、services/<模块>.zs、routes/<模块>*.zs、queries/<模块>_*.sql、tests/<模块>_*；STRICT_SCOPE，写 / 删之前就按它拦。
- 规划说明 PLAN_SYSTEM：prompts/role.md + DSL 速查（agents/shared/cheat.md）+ prompts/verbs.md + prompts/notes.md + 示例 prompts/example.zs。
"""
import re
from pathlib import Path

from .. import code as K
from ... import promptfile as PF
from . import contract as C
from . import project as P

NAME = "dslproj"
HERE = Path(__file__).resolve().parent
TASK_DESC = "做 DSL 项目里的一个模块"
PACK_DESC = "模块约定 + 上游公开函数头 + 现有骨架 + DSL 项目写法速查"

VERB_PACKS = ("code", "dslproj")
VERBS = ("列文件", "搜索代码", "读片段", "改文件", "写文件", "删文件", "加载检查", "比对约定", "跑用例")
WRITE_VERBS = ("改文件", "写文件", "删文件")
STRICT_SCOPE = True


def _prompt(name):
    return (HERE / "prompts" / name).read_text(encoding="utf-8").strip("\n")


FIX_SYSTEM = _prompt("fix_system.md")
SYNTAX = _prompt("syntax.md")


def PLAN_SYSTEM(engine=None):
    """整份规划 system：角色 + DSL 速查 + 动词 + 要点 + 示例 .zs + 输出要求。"""
    cheat = PF.shared("cheat.md").replace("用包 common text code", "用包 common text code dslproj")
    role = _prompt("role.md")
    if engine == "grok":
        role = role.replace("- 需要时用 dsl 工具读：读片段、搜索代码、查引用；", "- 需要时用你自带的只读工具读；")
    return "\n\n".join([role, cheat, _prompt("verbs.md"), _prompt("notes.md"),
                        "## 示例\n分支式规划的写法示例：只示意写法，不是答案。\n\n" + _prompt("example.zs"),
                        "## 输出\n- 只输出 .zs 脚本本身（含末尾的 #改法 段），不要代码围栏、不要解释文字\n"
                        "- 每条语句只占一行；派任务 / 问JSON 的提示词里不能换行；带空格的值先 设 成变量再写 {变量}\n"
                        "- #改法 里的原文逐字抄自读到的文件：含缩进，不带行号前缀，在文件里唯一"])


files = K.files


def scope_for(task, project, given=None):
    m = P.module_of(task)
    return P.scope_globs(m) if m else []


def _read(project, rel, cap=12000):
    f = Path(project) / rel
    if not f.is_file():
        return None
    t = f.read_text(encoding="utf-8", errors="replace")
    return t if len(t) <= cap else t[:cap] + "\n…（文件过长，后面略）"


def current_files(project, module):
    """范围内现有文件 → [(相对路径, 内容)]。"""
    root = Path(project)
    out = []
    for rel in sorted({str(f.relative_to(root)) for g in P.scope_globs(module) for f in root.glob(g) if f.is_file()}):
        if rel.startswith("tests/"):
            continue
        out.append((rel, _read(project, rel)))
    return out


def _numbered(text):
    return "\n".join(f"{i:4d}| {l}" for i, l in enumerate(text.splitlines(), 1))


def materials(task, project, scope):
    module = P.require_module(task)
    c, text = P.load_contract(project, module)
    parts = [f"## 本次要做的模块：{module}\n允许写 / 删的路径：{'、'.join(scope or P.scope_globs(module))}",
             f"## 本模块约定（contracts/{module}.md，冻结，不能改）\n```\n{text.strip()}\n```"]
    ups = []
    for d in c["依赖"]:
        uc, _ = C.parse(P.contract_path(project, d).read_text(encoding="utf-8"))
        ups.append(f"### 上游模块 {d}\n```\n{C.public_heads(uc)}\n```")
    parts.append("## 上游模块的公开函数（只能按这些函数头调用，且本模块「依赖」要写上；上游的文件不在范围内）\n"
                 + ("\n\n".join(ups) if ups else "（本模块没有依赖）"))
    cur = current_files(project, module)
    shown = []
    for rel, t in cur:
        shown.append(f"### {rel}（共 {len(t.splitlines())} 行）\n```\n{_numbered(t)}\n```")
    parts.append("## 本模块现有文件（行号前缀不是内容）\n" + ("\n\n".join(shown) if shown else "（还没有文件）"))
    parts.append(SYNTAX)
    return {"text": "\n\n".join(parts), "记录": {"模块": module, "约定函数": [f["名"] for f in c["函数"]], "依赖": c["依赖"],
                                              "现有文件": [r for r, _ in cur]}}


def accept(project, ctx):
    """验收：加载检查 + 比对约定 + 用例。返回 {通过, 问题, 摘要}。"""
    try:
        module = P.require_module(ctx["task"])
        c, _ = P.load_contract(project, module)
    except P.ProjError as e:
        return {"通过": False, "问题": [str(e)], "摘要": str(e)}
    mods = P.all_modules(project)
    probs = []
    load = P.load_problems(project, module, mods)
    probs += [f"加载检查：{p}" for p in load]
    cmp = P.compare(project, module, c, mods)
    probs += [f"比对约定：{d}" for d in cmp["差异"]]
    from . import cases as CASES          # 延迟 import：python -m ...dslproj.cases 直接跑它时不重复加载
    r = CASES.run(project, module)
    probs += [f"用例 {f['名']}：{f['原因']}" for f in r["失败"]]
    if r["原因"] and not r["失败"]:
        probs.append(f"跑用例：{r['原因']}")
    summary = (f"加载检查 {len(load)} 条问题；比对约定 {'一致' if cmp['一致'] else str(len(cmp['差异'])) + ' 条差异'}；"
               f"用例 {r['总数'] - len(r['失败'])}/{r['总数']} 通过")
    return {"通过": not probs, "问题": probs, "摘要": summary + ("\n" + "\n".join(probs) if probs else "")}


def fix_input(project, ctx, probs):
    """补改入参：任务 + 约定 + 上游公开函数头 + 验收问题 + 本模块现有文件 + 写法速查。"""
    module = P.module_of(ctx["task"])
    c, text = P.load_contract(project, module)
    ups = [f"### {d}\n{C.public_heads(C.parse(P.contract_path(project, d).read_text(encoding='utf-8'))[0])}" for d in c["依赖"]]
    cur = "\n\n".join(f"### {rel}\n```\n{_numbered(t)}\n```" for rel, t in current_files(project, module)) or "（还没有文件）"
    return "\n\n".join([f"【任务原文】\n{ctx['task']}", f"【本模块约定（不能改）】\n{text.strip()}",
                        "【上游模块公开函数】\n" + ("\n\n".join(ups) or "（无）"),
                        "【验收发现的问题】\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(probs, 1)),
                        f"【本模块现有文件的完整当前内容（行号前缀不是内容）】\n{cur}", SYNTAX])


def plan_problems(main, body, cl, generic):
    """计划检查：通用问题 + 计划里要有 跑用例（终止 成功 前自查；缺了只会把问题留给验收）。"""
    probs = list(generic)
    if not re.search(r"(^|=\s*)跑用例\b", body, re.M):
        probs.append("计划里没有 跑用例（套上改法后要 加载检查、比对约定、跑用例，全过才 终止 成功）")
    return probs
