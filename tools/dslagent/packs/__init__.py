"""资料包（pack）：v2 规划核心按任务类型插拔的全部差异都在这里声明。选择：run(pack=…) / 命令行 --pack / 环境变量 DSLAGENT_PACK（缺省 code）。

核心（v2.py）只认下面这套接口，不知道资料是什么、动词是什么、怎么验收。一个包 = 本目录下的一个模块（code.py）或子包（dslproj/），
在 REGISTRY 里登记名字即可。怎么写一个新包见 packs/README.md。

声明（模块级名字；带「可选」的可以不写）：
  NAME                  str，包名（= --pack / DSLAGENT_PACK 的值）。
  资料（可选）  materials(task, project, scope) -> {"text": 拼进规划 user 的文本, "记录": {…并进 result.json 的 v2.*}}
        给规划模型看什么（确定性，不调模型）。scope 是最终的范围 glob 列表（可能为空）。不实现 materials 时认旧名 plan_outline(task, project)；都没有 = 规划只看任务原文。
  动词  VERBS           该包计划里放开的任务类型动词名（语句 / 动词白名单 = plan.BASE_VERBS ∪ VERBS，不再写死）。
        VERB_PACKS      脚本里「用包」可写的包名（缺省 ("code",)；common / text 总是可用）。动词本身放在 tools/dslagent/verbs/<包>/defs/。
        WRITE_VERBS     会写 / 删项目文件的动词（必须 ⊂ VERBS）；它们在核心里统一按范围拦截（scope.guard，经 reason.check）。
        GATED_VERBS     （可选，缺省空）计划里「只在结果会改变走向时才真跑」的动词（v2.test_gate；code = ("跑测试",)）。
  验收  二选一：
        accept(project, ctx) -> {"通过": bool, "问题": [文字…], "摘要": 可选文字}
            简单验收：核心用 verify/simple.py 包成完整验收——有问题派 1 次补改（edits 套用），补改后再 accept 一次。
            ctx = {task, scope, stage("验收"|"补改后"), out, changed(改动文件), base, cur, main}。
        verifier() -> 完整验收对象（接口见 verify/__init__.py：prepare / check / fix / boundary …）；code 用它（全量测试 + 边界复核）。
        补改相关（可选，仅 accept 方式）：FIX_SYSTEM（补改 system，缺省通用文本）、fix_input(project, ctx, problems) -> user 文本。
  范围  scope_for(task, project, given) -> [glob…]  允许写 / 删的路径（`a/` 目录 / `a/b.py` 精确 / `routes/x*` 通配，见 scope.py）；
        没有或返回空 = 不启用范围闸（code 就是这样）。命令行 --scope / run(scope=) 优先。
        STRICT_SCOPE = True（可选，缺省 False）：写类动词（WRITE_VERBS）和补改套用在写之前就按范围拦（scope.guard，范围外的写直接被拒、模型当场看到原因）；
        缺省只做事后闸（执行后快照对比，范围外的改动恢复成改前内容并要求补改，code 的老行为）。
  规划说明  PLAN_SYSTEM  str | callable(engine) -> str：整份规划 system（含这类任务的要点 + 示例 .zs）。不写就用 agents/plan.md（code 的）并按
        RULES_KEY（缺省 NAME）取 agents/shared/plan_rules_<KEY>.md / _end / _table 三段规则（PLAN_RULES / PLAN_RULES_END 是前两段的原文）。
  计划检查（可选）  plan_problems(main, body, cl, generic) -> list[str]：计划静态检查里包专属的问题（generic 是核心已查出的通用问题）。
  其它（可选）  files(project) 迭代 (相对路径, 绝对路径)：要做快照的文件（缺省 = 项目里的文本文件）；TASK_DESC / PACK_DESC 说明性文字。
  旧名兼容：EXTRA_VERBS / EXTRA_PACKS（newproj 在用：在旧白名单 ALLOWED_VERBS 之上额外放开）。

校验：validate(pack) 列出声明里的问题（缺字段、动词不存在、WRITE_VERBS 不在 VERBS 里……），v2.run 启动时调用，有问题直接判失败。
"""
import importlib
import os

REGISTRY = {"code": "tools.dslagent.packs.code", "newproj": "tools.dslagent.packs.newproj",
            "dslproj": "tools.dslagent.packs.dslproj"}
DEFAULT = "code"


def available():
    return sorted(REGISTRY)


def pick(name):
    """按取值拿资料包模块；不认识的名字报 ValueError（列出可用的）。也接受已经是包对象的参数（原样返回）。"""
    if name is not None and not isinstance(name, str):
        return name
    n = (name or DEFAULT).strip().lower() or DEFAULT
    if n not in REGISTRY:
        raise ValueError(f"资料包名字不对：{name!r}，可用：{'、'.join(available())}（--pack / DSLAGENT_PACK）")
    return importlib.import_module(REGISTRY[n])


def current():
    """环境变量 DSLAGENT_PACK 选的资料包（缺省 code）。"""
    return pick(os.environ.get("DSLAGENT_PACK"))


# ------------------------------------------------------------------ 由声明生成核心要用的东西


def verbs_of(pack):
    """计划里允许的动词名：声明了 VERBS 就是 BASE ∪ VERBS（∪ EXTRA_VERBS）；没声明（newproj 这类旧包）= 旧白名单 ∪ EXTRA_VERBS。"""
    from .. import plan as DP
    if hasattr(pack, "VERBS"):
        return set(DP.BASE_VERBS) | set(pack.VERBS) | set(getattr(pack, "EXTRA_VERBS", ()))
    return set(DP.ALLOWED_VERBS) | set(getattr(pack, "EXTRA_VERBS", ()))


def use_of(pack):
    """脚本里「用包」可写的包名。"""
    vp = tuple(getattr(pack, "VERB_PACKS", ("code",)))
    return tuple(dict.fromkeys(("common", "text") + vp + tuple(getattr(pack, "EXTRA_PACKS", ()))))


def materials_of(pack, task, project, scope=None):
    """资料：{"text", "记录"}；包没有 materials / plan_outline 就是空文本（规划只看任务原文）。"""
    if hasattr(pack, "materials"):
        o = pack.materials(task, project, list(scope or []))
    elif hasattr(pack, "plan_outline"):
        o = pack.plan_outline(task, project)
    else:
        return {"text": "", "记录": {}}
    return {"text": o.get("text") or "", "记录": o.get("记录") or {}}


def scope_of(pack, task, project, given=None):
    """允许改动的路径 glob 列表：given（命令行 / 参数）优先，其次包的 scope_for，都没有 = []（不启用）。"""
    from .. import scope as SC
    g = SC.parse(given)
    if g:
        return g
    if hasattr(pack, "scope_for"):
        return SC.parse(pack.scope_for(task, project, given))
    return []


def verifier_of(pack):
    """完整验收对象：DSLAGENT_VERIFY 显式指定的 > 包的 verifier() > 包的 accept 包成的简单验收 > verify 注册表里同名的。"""
    from .. import verify
    v = (os.environ.get("DSLAGENT_VERIFY") or "").strip()
    if v:
        return verify.pick(v)
    if hasattr(pack, "verifier"):
        return pack.verifier()
    if hasattr(pack, "accept"):
        from ..verify.simple import Simple
        return Simple(pack)
    return verify.pick(pack.NAME)


def validate(pack):
    """声明校验 → 问题列表（空 = 合格）。"""
    from .. import plan as DP
    probs = []
    if not isinstance(getattr(pack, "NAME", None), str) or not pack.NAME:
        probs.append("缺 NAME（包名）")
    if not hasattr(pack, "VERBS"):
        probs.append("缺 VERBS（动词白名单）")
    else:
        known = set(DP.ALL_VERBS) | set(DP.BASE_VERBS)
        bad = sorted(v for v in pack.VERBS if v not in known)
        if bad:
            probs.append(f"VERBS 里的动词不存在（verbs/*/defs/ 下没有）：{'、'.join(bad)}")
        wv = set(getattr(pack, "WRITE_VERBS", ()))
        if wv - set(pack.VERBS):
            probs.append(f"WRITE_VERBS 必须是 VERBS 的子集：{'、'.join(sorted(wv - set(pack.VERBS)))}")
        gv = set(getattr(pack, "GATED_VERBS", ()))
        if gv - set(pack.VERBS):
            probs.append(f"GATED_VERBS 必须是 VERBS 的子集：{'、'.join(sorted(gv - set(pack.VERBS)))}")
    root = DP.PKG / "verbs"
    for p in getattr(pack, "VERB_PACKS", ("code",)):
        if not (root / p).is_dir():
            probs.append(f"VERB_PACKS 里的动词包 {p} 不存在（tools/dslagent/verbs/{p}/）")
    if not (hasattr(pack, "accept") or hasattr(pack, "verifier") or os.environ.get("DSLAGENT_VERIFY")):
        probs.append("缺验收：要写 accept(project, ctx) 或 verifier()")
    if not (hasattr(pack, "PLAN_SYSTEM") or hasattr(pack, "PLAN_RULES")):
        probs.append("缺规划说明：要写 PLAN_SYSTEM（或 code 式的 PLAN_RULES）")
    for fn in ("materials", "accept", "verifier", "scope_for", "plan_problems", "files"):
        if hasattr(pack, fn) and not callable(getattr(pack, fn)):
            probs.append(f"{fn} 必须是函数")
    return probs
