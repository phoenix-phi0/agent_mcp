"""newproj --modular：顶层规划 → 层次 × 模块 → 按层逐层构建（旧 newproj / split / layered 不动）。

对照真实项目 kg/ 的七层：能力层 verbs/（现成 Python 动词）、数据层 entities/<模块>.entity、查询层 queries/<模块>_*.sql、
流程层 scripts/<名>.zs（多个接口共用的业务流程）、接口层 routes/<模块>.zs、界面层 ui/<页>.ui。调用方向 界面→接口→流程→查询→数据，能力层任何层可用，不许往上调。

流程（v2.run_newproj(modular=True) 调 run_modular()）：
  0 能力清单（程序）：用 VerbRegistry 加载 verbs/ 下每个包，抽出动词名 / 参数 / 一句话说明 → capabilities.md（输出目录）。
  1 顶层规划（模型 1 次，不过重写，共 ≤2 次）：模型用 DSL 写 plan/top.zs（目标 / 使用者 / 主流程 / 模块（依赖）/ 共用流程归属 / 横切 / 构建顺序，见 plandsl.py），程序解析成 dict 后 validate_top 校验 → PLAN.md。
  2 层次 × 模块（模型 1 次，≤2 次）：plan/layers.zs，每模块一个块（规则 / 数据 / 流程 / 接口 / 界面 / 能力 / 缺口）；validate_split 校验（与顶层模块一致等）→ LAYERS.md。
  2.5 接口约定（contract=True，v2 默认开；--no-contract 走原来的逐文件规划）：数据层做完后，按构建顺序每个模块一次调用写出该模块的约定（sql / 流程 / 接口 / 界面的名字、参数、返回、响应键，
    见 contract.py），程序校验（引用 / 参数 / 层次 / 动词 / 规则）不过带报错重写（≤2 次），全部通过写 CONTRACTS.md + contracts.json（从骨架生成的只读产物）并冻结约定部分的快照（contracts_frozen.json）；约定的源头是模型写的骨架文件（见 skeleton.py）；
    之后查询 / 流程 / 接口 / 界面各文件只按自己的约定项实现（计划直接由约定派生，不再另外规划），检查加上「与约定一致」，文件之间互不依赖、不因别的文件失败而跳过；
    全部实现后统一试调一轮（见 trial.py），不过的接口文件（及报错点到名的流程 / sql）带报错重写 1 轮。
  3 逐层构建，层内按顶层「构建顺序」逐模块：数据（建库＋gen 增删改查＋检查项目）→ 查询 → 流程 → 接口 → 界面。每个文件先单独规划（≤2 次）再生成（≤2 次）。
    失败的文件撤回、记失败，依赖它的上层文件跳过；超长 / 被杀＝该文件失败不终止；花费熔断（--cost-cap）沿用。
  4 整体检查：检查项目 + 全部 zs 的动词 / 参数 / 调用核对 → 成功 / 部分成功 / 失败。
模型调用、单文件失败隔离、熔断、检查动词（校验实体 / 预编译sql / 检查项目 / 校验角色 / 核对规则 / 参数核对）都复用 layered.py。

从已有规划开始（run_modular(from_plan=load_plan(旧输出目录))，CLI --from-plan）：读回旧运行的规划（plan/top.zs、plan/layers.zs；旧版 JSON 目录也读，转成 DSL 规划文件），跳过前两步，在新目录从数据层做起。
继续构建（run_modular(resume=…)，CLI newproj --modular --resume）：不重做顶层规划与层次×模块（读 out/plan/top.zs、plan/layers.zs，可手改；旧产物读 top.json / split.json，再不行从 result.json 与 calls/ 里的原始回复还原，见 restore_state），
已「通过」且仍在磁盘、仍过检查的文件跳过（状态从文件的「产出」或 calls/ 里的规划回复还原），「失败」「跳过」「未做」的按原顺序重做（失败的带上次失败原因当报错）；
--cost-cap 只算本次新花的，result.json 保留上次记录（v2.运行 逐次累加），calls.json 追加并给每条标 run 序号。
"""
import contextlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import contract as C
from . import layered as LY
from . import plandsl as PD
from . import skeleton as SK
from . import guard as G      # noqa: F401
from . import loadcheck as LC
from . import trial as TR
from .layered import FileFail, Halt, _Retry

if str(LY.DEFS) not in sys.path:
    sys.path.insert(0, str(LY.DEFS))
import _layer as L      # noqa: E402
import _lstep as S      # noqa: E402
import _params as P      # noqa: E402
from tools.dsl_core import KEYWORDS, normalize, split_head      # noqa: E402

PKG = Path(__file__).resolve().parent
VERBS_ROOT = PKG.parents[1] / "verbs"          # 项目运行时 `用包` 找的现成动词包（不是 dslagent 自己的 verbs/）
SNAKE = L.SNAKE
IDENT = re.compile(r"^[A-Za-z_]\w*$")
ALL_LAYERS = ("能力", "数据", "查询", "流程", "接口", "界面")
BUILD_LAYERS = ("数据", "查询", "流程", "接口", "界面")
FIELD_TYPES = ("文本", "长文本", "整数", "小数", "日期", "布尔", "枚举")
GAP_WAYS = ("sql", "流程", "待补")
ACCOUNT_ENTS = ("user", "users", "account", "accounts")
DEFAULT_PACKS = ("db", "http", "common")
SKIP_PACKS = ("probe",)
HEAD_OK = set(KEYWORDS.values())
NO_REGISTER_RE = re.compile(r"(不(?:能|得|可|许|允许|开放|支持|提供).{0,8}(?:自己|自助|自行|公开|自由)?.{0,3}注册|(?:禁止|关闭|取消|去掉).{0,6}注册|无法.{0,6}注册"
                            r"|(?:账号|账户|学生|学习者|用户).{0,10}(?:由|靠|须由).{0,3}(?:教师|老师|管理员).{0,6}(?:建|创建|开通|添加|新增|导入)|(?:教师|老师|管理员).{0,4}(?:统一)?(?:建|创建|开通)(?:账号|账户|学生))")
CALL_RE = re.compile(r"^(?:设\s+\S+\s*=\s*)?(执行|后台执行)\s+(scripts/\S+?\.zs)(?:\s+(.*))?$")
KV_RE = re.compile(r"(\w+)=(\{[^{}]*\}|\S+)")
RET_KEYS = re.compile(r'"(\w+)"\s*:')


def _prompt(name):
    return LY._prompt(name)


def _strs(v, what, errs):
    return S._strs(v, what, errs)


def _dedup(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


# ================================================================== 0 能力清单

def capabilities(verbs_root=None):
    """{包: [{名, 参数:[…], 说明}]}：加载 verbs/ 下每个包（不含 probe），取动词名、参数名、一句话说明。"""
    from tools.verbs import VerbRegistry
    root = Path(verbs_root or VERBS_ROOT)
    reg = VerbRegistry()
    ws = Path(tempfile.gettempdir())
    packs = [d.name for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(("_", ".")) and d.name not in SKIP_PACKS
             and (any(d.glob("*.zs")) or (d / "_verbs.py").is_file())] if root.is_dir() else []
    for p in packs:
        reg.load_pack(root / p, ws)
    out = {p: [] for p in packs}
    for name in reg.names():
        pack = reg.pack_of(name)
        if pack not in out:
            continue
        impl = reg._verbs[name][2]
        if reg.kind_of(name) == "python":
            desc = (getattr(impl, "__verb_description__", "") or "").strip().splitlines()[0:1]
        else:
            lines = [l.lstrip("#").strip() for l in Path(impl).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip().startswith("#")]
            desc = lines[:1]
        out[pack].append({"名": name, "参数": reg.params_of(name), "说明": desc[0] if desc else ""})
    return out


def _params_brief(params):
    keep = [p for p in params if not re.fullmatch(r"参数[一二三四五六七八九十]", p)]
    return ",".join(keep) + ("[,k=v…]" if len(keep) != len(params) else "")


def cap_markdown(caps):
    out = ["# 能力清单（verbs/ 现成动词）", "", "项目里写 `用包 <包名>` 后才能用该包的动词；清单之外的动词不存在（未知动词会静默变成字面字符串）。", ""]
    for p, vs in caps.items():
        out += [f"## {p}（{len(vs)} 个）", ""]
        out += [f"- `{v['名']}({_params_brief(v['参数'])})` {v['说明']}".rstrip() for v in vs]
        out.append("")
    return "\n".join(out)


def cap_text(caps, packs=None, brief=False):
    """给提示词用的紧凑文本。brief：只列动词名（顶层规划 / 层次拆分用）。"""
    lines = []
    for p, vs in caps.items():
        if packs is not None and p not in packs:
            continue
        if brief:
            lines.append(f"{p}: " + " ".join(v["名"] for v in vs))
        else:
            lines.append(f"[{p}]")
            lines += [f"  {v['名']}({_params_brief(v['参数'])}) {v['说明'][:60]}".rstrip() for v in vs]
    return "\n".join(lines) or "（无）"


def verb_packs(caps):
    return {v["名"]: p for p, vs in caps.items() for v in vs}


# ================================================================== 1 顶层规划

def closure(deps, m):
    """m 直接 + 间接依赖的模块集合（不含自己）。"""
    seen, todo = set(), list(deps.get(m, ()))
    while todo:
        d = todo.pop()
        if d not in seen:
            seen.add(d)
            todo += deps.get(d, ())
    return seen


def _find_cycle(deps):
    state = {}

    def visit(n, path):
        state[n] = 1
        for d in deps.get(n, ()):
            if state.get(d) == 1:
                return path + [n, d]
            if d not in state:
                c = visit(d, path + [n])
                if c:
                    return c
        state[n] = 2
        return None
    for n in deps:
        if n not in state:
            c = visit(n, [])
            if c:
                return c
    return None


def validate_top(x, packs, task=""):
    """顶层规划校验。返回 {ok, errors, top}；top 是规范化后的对象。packs：真实存在的包名集合。"""
    obj, err = L.parse(x)
    if err:
        return {"ok": False, "errors": [err.replace("清单", "顶层规划")], "top": None}
    errs = []
    goal = str(obj.get("目标") or "").strip()
    if not goal:
        errs.append("要有「目标」（一句话）")
    u = obj.get("使用者")
    roles, people = [], ""
    if not isinstance(u, dict):
        errs.append("「使用者」要是 {\"角色\":[…],\"人数\":\"单人|多人\"}")
    else:
        roles = _strs(u.get("角色"), "使用者.角色", errs)
        people = str(u.get("人数") or "").strip()
        if people not in ("单人", "多人"):
            errs.append("使用者.人数 只能是 单人 或 多人")
        for r in roles:
            if not SNAKE.match(r):
                errs.append(f"角色「{r}」要是英文小写 snake")
        if len(set(roles)) != len(roles):
            errs.append("使用者.角色 有重复项")
        if not roles and task and L.ROLE_HINT.search(str(task)):
            errs.append("需求里提到了登录 / 账号 / 角色 / 权限，使用者.角色 必须给出（如 [\"teacher\",\"student\"]）")
    mods, deps, desc = [], {}, {}
    raw = obj.get("模块")
    if not isinstance(raw, list) or not raw:
        errs.append("「模块」要是非空列表，每项 {名, 说明, 依赖}")
        raw = []
    for i, m in enumerate(raw, 1):
        if not isinstance(m, dict):
            errs.append(f"模块第 {i} 项要是对象")
            continue
        n = m.get("名")
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"模块名「{n}」要是英文小写 snake")
            continue
        if n in deps:
            errs.append(f"模块名「{n}」重复")
            continue
        mods.append(n)
        deps[n] = _strs(m.get("依赖"), f"模块「{n}」的依赖", errs)
        desc[n] = str(m.get("说明") or "")
    for n in mods:
        for d in deps[n]:
            if d == n:
                errs.append(f"模块「{n}」依赖了自己")
            elif d not in deps:
                errs.append(f"模块「{n}」的依赖「{d}」不在模块表里（模块：{mods}）")
    if not errs:
        cyc = _find_cycle(deps)
        if cyc:
            errs.append("模块依赖成环：" + " → ".join(cyc))
    flows = []
    fl = obj.get("主流程")
    if not isinstance(fl, list) or not fl:
        errs.append("「主流程」要是非空列表，每项 {名, 角色, 步骤, 经过模块}")
        fl = []
    for i, f in enumerate(fl, 1):
        if not isinstance(f, dict) or not str(f.get("名") or "").strip():
            errs.append(f"主流程第 {i} 项要有「名」")
            continue
        via = _strs(f.get("经过模块"), f"主流程「{f['名']}」的经过模块", errs)
        if not via:
            errs.append(f"主流程「{f['名']}」要写经过模块")
        for v in via:
            if v not in deps:
                errs.append(f"主流程「{f['名']}」经过的模块「{v}」不存在（模块：{mods}）")
        role = str(f.get("角色") or "").strip()
        if role and roles and role not in roles:
            errs.append(f"主流程「{f['名']}」的角色「{role}」不在使用者.角色 {roles} 里")
        flows.append({"名": str(f["名"]).strip(), "角色": role, "步骤": _strs(f.get("步骤"), f"主流程「{f['名']}」的步骤", errs), "经过模块": via})
    shared = []
    sf = obj.get("共用流程")
    if sf in (None, ""):
        sf = []
    if not isinstance(sf, list):
        errs.append("「共用流程」要是列表（没有就写 []）")
        sf = []
    seen_sf = set()
    for i, s in enumerate(sf, 1):
        if not isinstance(s, dict):
            errs.append(f"共用流程第 {i} 项要是对象")
            continue
        fn, owner = s.get("流程名"), s.get("归属模块")
        if not isinstance(fn, str) or not SNAKE.match(fn):
            errs.append(f"共用流程名「{fn}」要是英文小写 snake")
            continue
        if fn in seen_sf:
            errs.append(f"共用流程「{fn}」重复")
        seen_sf.add(fn)
        users = _strs(s.get("被用于"), f"共用流程「{fn}」的被用于", errs)
        if owner not in deps:
            errs.append(f"共用流程「{fn}」的归属模块「{owner}」不是已知模块")
            continue
        if not users:
            errs.append(f"共用流程「{fn}」要写被用于（哪些模块用它）")
        for um in users:
            if um not in deps:
                errs.append(f"共用流程「{fn}」的使用方「{um}」不是已知模块")
            elif um == owner:
                errs.append(f"共用流程「{fn}」的使用方不用写归属模块自己（{owner}）")
            elif owner not in closure(deps, um):
                errs.append(f"共用流程「{fn}」的使用方「{um}」没有依赖归属方「{owner}」（先在模块依赖里补上，或把流程归属换到被依赖的模块）")
        shared.append({"流程名": fn, "归属模块": owner, "被用于": users})
    cross = obj.get("横切")
    cut = {}
    if not isinstance(cross, dict):
        errs.append("「横切」要是对象：{账号与权限, 调模型, 后台任务, 内容数据导入, 全局约束}")
    else:
        cut["账号与权限"] = str(cross.get("账号与权限") or "").strip()
        if not cut["账号与权限"]:
            errs.append("横切.账号与权限 要写（无登录就写「无账号」）")
        models = []
        for i, c in enumerate(cross.get("调模型") or [], 1):
            if not isinstance(c, dict):
                errs.append(f"横切.调模型 第 {i} 项要是 {{处, 包}}")
                continue
            pk = str(c.get("包") or "").strip()
            if pk not in packs:
                errs.append(f"横切.调模型「{c.get('处')}」用的包「{pk}」不存在（现有包：{sorted(packs)}）")
            models.append({"处": str(c.get("处") or ""), "包": pk})
        cut["调模型"] = models
        cut["后台任务"] = _strs(cross.get("后台任务"), "横切.后台任务", errs)
        cut["内容数据导入"] = str(cross.get("内容数据导入") or "").strip()
        cut["全局约束"] = _strs(cross.get("全局约束"), "横切.全局约束", errs)
    order = _strs(obj.get("构建顺序"), "「构建顺序」", errs)
    if not errs:
        if sorted(order) != sorted(mods) or len(set(order)) != len(order):
            errs.append(f"构建顺序要恰好包含全部模块各一次：{mods}（现在 {order}）")
        else:
            pos = {n: i for i, n in enumerate(order)}
            for n in mods:
                for d in deps[n]:
                    if pos[d] > pos[n]:
                        errs.append(f"构建顺序不是依赖的拓扑序：「{n}」依赖「{d}」，但「{d}」排在它后面")
    if errs:
        return {"ok": False, "errors": errs, "top": None}
    top = {"目标": goal, "使用者": {"角色": roles, "人数": people}, "主流程": flows,
           "模块": [{"名": n, "说明": desc[n], "依赖": deps[n]} for n in mods], "共用流程": shared, "横切": cut, "构建顺序": order}
    return {"ok": True, "errors": [], "top": top}


def top_deps(top):
    return {m["名"]: list(m["依赖"]) for m in top["模块"]}


def plan_md(top):
    deps = top_deps(top)
    L_ = [f"# 顶层规划（PLAN）", "", f"**目标**：{top['目标']}", "",
          f"**使用者**：角色 {('、'.join(top['使用者']['角色']) or '无（不登录）')}；{top['使用者']['人数']}", "", "## 主流程", ""]
    for f in top["主流程"]:
        L_.append(f"- **{f['名']}**（{f['角色'] or '不限角色'}）：{' → '.join(f['步骤'])}；经过模块 {'、'.join(f['经过模块'])}")
    L_ += ["", "## 模块依赖", "", "| 模块 | 说明 | 依赖 |", "|---|---|---|"]
    L_ += [f"| {m['名']} | {m['说明']} | {'、'.join(m['依赖']) or '—'} |" for m in top["模块"]]
    L_ += ["", "依赖图（A → B 表示 A 依赖 B，B 先建）：", ""]
    L_ += [f"- {n} → {'、'.join(d) or '（无）'}" for n, d in deps.items()]
    L_ += ["", "## 共用流程归属", ""]
    L_ += [f"- `{s['流程名']}` 归属 {s['归属模块']}，被 {'、'.join(s['被用于'])} 用" for s in top["共用流程"]] or ["- （无）"]
    c = top["横切"]
    L_ += ["", "## 横切", "", f"- 账号与权限：{c['账号与权限']}"]
    L_ += [f"- 调模型：{x['处']}（包 {x['包']}）" for x in c["调模型"]] or ["- 调模型：无"]
    L_ += [f"- 后台任务：{t}" for t in c["后台任务"]] or ["- 后台任务：无"]
    L_ += [f"- 内容数据导入：{c['内容数据导入'] or '无'}", "- 全局约束：" + ("；".join(c["全局约束"]) or "无")]
    L_ += ["", "## 构建顺序", "", " → ".join(top["构建顺序"]), ""]
    return "\n".join(L_)


# ================================================================== 2 层次 × 模块

def validate_split(x, top, caps, task=""):
    """层次×模块校验。返回 {ok, errors, split}。top：validate_top 规范化后的顶层规划。"""
    obj, err = L.parse(x)
    if err:
        return {"ok": False, "errors": [err.replace("清单", "层次×模块")], "split": None}
    packs = set(caps)
    vp = verb_packs(caps)
    errs = []
    tpl = str(obj.get("模板") or "").strip()
    if tpl not in L.TEMPLATES:
        errs.append(f"模板「{tpl}」不对，只能是 {' / '.join(L.TEMPLATES)}")
    roles = _strs(obj.get("角色"), "「角色」", errs)
    top_roles = top["使用者"]["角色"]
    if roles and tpl != "private":
        errs.append("给了「角色」，模板必须是 private")
    if set(roles) != set(top_roles):
        errs.append(f"角色 {roles} 与顶层规划的使用者.角色 {top_roles} 不一致")
    for r in roles:
        if not SNAKE.match(r):
            errs.append(f"角色「{r}」要是英文小写 snake")
    if top_roles and tpl != "private":
        errs.append("顶层规划有角色，模板必须是 private")
    private = tpl == "private"
    layer_raw = obj.get("层")
    layer_desc = {}
    if isinstance(layer_raw, list):
        layer_raw = {str(i): "" for i in layer_raw}
    if not isinstance(layer_raw, dict) or not layer_raw:
        errs.append("「层」要是对象：{层名: 一句话职责}，层名从 " + "/".join(ALL_LAYERS) + " 里选")
        layer_raw = {}
    for k, v in layer_raw.items():
        if k not in ALL_LAYERS:
            errs.append(f"层「{k}」不对，只能从 {'/'.join(ALL_LAYERS)} 里选")
        layer_desc[k] = str(v or "")
    if layer_raw and "数据" not in layer_raw:
        errs.append("「层」必须包含「数据」")
    glob = _strs(obj.get("全局约束"), "「全局约束」", errs)

    tmods = {m["名"]: m for m in top["模块"]}
    raw = obj.get("模块")
    if not isinstance(raw, list) or not raw:
        errs.append("「模块」要是非空列表")
        raw = []
    mods, names = {}, []
    for i, m in enumerate(raw, 1):
        if not isinstance(m, dict) or not isinstance(m.get("名"), str):
            errs.append(f"模块第 {i} 项要有「名」")
            continue
        n = m["名"]
        if n in mods:
            errs.append(f"模块「{n}」重复")
            continue
        names.append(n)
        mods[n] = m
    for n in names:
        if n not in tmods:
            errs.append(f"模块「{n}」不在顶层规划里（顶层模块：{sorted(tmods)}），不许多出模块")
    for n in tmods:
        if n not in mods:
            errs.append(f"顶层规划的模块「{n}」没有出现（不许少模块）")
    seen = {"实体": {}, "流程": {}, "接口文件": {}, "界面": {}}

    def claim(kind, name, owner, what):
        if not isinstance(name, str) or not SNAKE.match(name):
            errs.append(f"{what}「{name}」要是英文小写 snake")
            return False
        if name in seen[kind]:
            errs.append(f"{what}「{name}」重复（已属于模块 {seen[kind][name]}，每个{kind}全项目唯一）" if kind == "实体" else f"{what}「{name}」重复（已在模块 {seen[kind][name]}）")
            return False
        seen[kind][name] = owner
        return True

    norm = {}
    rules_all, rules_of = {}, {}
    for n in top["构建顺序"]:
        if n not in mods:
            continue
        m = mods[n]
        r_texts = _strs(m.get("规则"), f"模块「{n}」的规则", errs)
        nums = []
        for t in r_texts:
            h = f"R{len(rules_all) + 1}"
            rules_all[h] = t
            nums.append(h)
        rules_of[n] = nums
        ents = _strs(m.get("数据"), f"模块「{n}」的数据", errs)
        for e in ents:
            if claim("实体", e, n, "实体") and private and e in ACCOUNT_ENTS:
                errs.append(f"实体「{e}」是账号表，private 模板由 gen 统一生成，不许在模块「{n}」里再列")
        flows = []
        fraw = m.get("流程") or []
        if not isinstance(fraw, list):
            errs.append(f"模块「{n}」的流程要是列表")
            fraw = []
        for f in fraw:
            if not isinstance(f, dict):
                errs.append(f"模块「{n}」的流程项要是 {{名, 作用, 用于, 调流程}}")
                continue
            fn = f.get("名")
            if claim("流程", fn, n, "流程名"):
                flows.append({"名": fn, "作用": str(f.get("作用") or ""), "用于": _strs(f.get("用于"), f"流程「{fn}」的用于", errs),
                              "调流程": _strs(f.get("调流程"), f"流程「{fn}」的调流程", errs)})
        ifaces = []
        for f in m.get("接口") or []:
            fn = f.get("文件") if isinstance(f, dict) else f
            what = str(f.get("作用") or "") if isinstance(f, dict) else ""
            if isinstance(fn, str) and not (fn == n or re.fullmatch(rf"{re.escape(n)}_[a-z0-9_]+", fn)):
                errs.append(f"接口文件「{fn}」要叫 {n} 或 {n}_<后缀>")
            elif claim("接口文件", fn, n, "接口文件"):
                ifaces.append({"文件": fn, "作用": what})
        uis = []
        for f in m.get("界面") or []:
            fn = f.get("名") if isinstance(f, dict) else f
            what = str(f.get("作用") or "") if isinstance(f, dict) else ""
            if claim("界面", fn, n, "界面名"):
                uis.append({"名": fn, "作用": what})
        cap = _strs(m.get("能力"), f"模块「{n}」的能力", errs)
        for p in cap:
            if p not in packs:
                errs.append(f"模块「{n}」的能力「{p}」不是现有包（现有：{sorted(packs)}）")
        gaps = []
        for g in m.get("缺口") or []:
            if not isinstance(g, dict) or not str(g.get("事") or "").strip():
                errs.append(f"模块「{n}」的缺口项要是 {{事, 办法, 用动词}}")
                continue
            way = str(g.get("办法") or "").strip()
            if way not in GAP_WAYS:
                errs.append(f"模块「{n}」缺口「{g['事']}」的办法「{way}」只能是 {'/'.join(GAP_WAYS)}")
            verbs = _strs(g.get("用动词"), f"缺口「{g['事']}」的用动词", errs)
            for v in verbs:
                if v not in vp:
                    errs.append(f"模块「{n}」缺口「{g['事']}」用的动词「{v}」不在能力清单里（不许编造；做不到就写办法=待补）")
            gaps.append({"事": str(g["事"]).strip(), "办法": way, "用动词": verbs})
            if way == "流程" and not flows:
                errs.append(f"模块「{n}」缺口「{g['事']}」办法写了「流程」，但本模块没有流程")
        norm[n] = {"名": n, "说明": tmods[n]["说明"] if n in tmods else "", "依赖": tmods[n]["依赖"] if n in tmods else [], "规则": r_texts, "规则号": nums,
                   "数据": ents, "流程": flows, "接口": ifaces, "界面": uis, "能力": cap, "缺口": gaps}
    # 层要覆盖用到的层
    used = {"数据": any(v["数据"] for v in norm.values()), "流程": any(v["流程"] for v in norm.values()),
            "接口": any(v["接口"] for v in norm.values()), "界面": any(v["界面"] for v in norm.values()),
            "查询": any(v["数据"] or v["流程"] or v["接口"] for v in norm.values())}
    for k, flag in used.items():
        if flag and layer_raw and k not in layer_raw and k != "查询":
            errs.append(f"模块里用到了「{k}」层，但「层」里没列它")
    if not used["数据"]:
        errs.append("所有模块的「数据」都是空：至少要有一个实体")
    # 流程规则：归属 / 使用方 / 调用方向
    deps = top_deps(top)
    shared = {s["流程名"]: s for s in top["共用流程"]}
    fmod = seen["流程"]
    ifile_mod = seen["接口文件"]
    called = set()
    for n, v in norm.items():
        for f in v["流程"]:
            for c in f["调流程"]:
                called.add(c)
                if c == f["名"]:
                    errs.append(f"流程「{f['名']}」调用了自己")
                elif c not in fmod:
                    errs.append(f"流程「{f['名']}」调用的流程「{c}」不存在")
                elif fmod[c] != n and not (c in shared and shared[c]["归属模块"] == fmod[c] and (n in shared[c]["被用于"]) and fmod[c] in closure(deps, n)):
                    errs.append(f"流程「{f['名']}」（模块 {n}）调了模块 {fmod[c]} 的流程「{c}」：只能调本模块的，或顶层「共用流程」规定给本模块用的")
    for sname, s in shared.items():
        if sname not in fmod:
            errs.append(f"顶层共用流程「{sname}」没有写在任何模块的流程里（应放在归属模块 {s['归属模块']}）")
        elif fmod[sname] != s["归属模块"]:
            errs.append(f"流程「{sname}」应放在顶层规定的归属模块 {s['归属模块']}，现在放在 {fmod[sname]}")
    for n, v in norm.items():
        for f in v["流程"]:
            allowed = {n}
            if f["名"] in shared:
                allowed = {shared[f["名"]]["归属模块"], *shared[f["名"]]["被用于"]}
            for u in f["用于"]:
                if u not in ifile_mod:
                    errs.append(f"流程「{f['名']}」的用于「{u}」不是任何模块的接口文件（接口文件：{sorted(ifile_mod)}）")
                elif ifile_mod[u] not in allowed:
                    errs.append(f"流程「{f['名']}」不能给模块 {ifile_mod[u]} 的接口「{u}」用（只许 {sorted(allowed)}；跨模块共用要先写进顶层「共用流程」）")
            if not f["用于"] and f["名"] not in called:
                errs.append(f"流程「{f['名']}」没有接口用它（用于为空）也没有别的流程调它，不要拆这个流程")
    if not errs:
        cyc = _find_cycle({f["名"]: f["调流程"] for v in norm.values() for f in v["流程"]})
        if cyc:
            errs.append("流程互调成环：" + " → ".join(cyc))
    if errs:
        return {"ok": False, "errors": errs, "split": None}
    order = [n for n in LAYERS_ORDER if n in layer_desc or used.get(n)]
    cap_final = {}
    for n, v in norm.items():
        extra = [vp[x] for g in v["缺口"] for x in g["用动词"]]
        cap_final[n] = _dedup([*(p for p in DEFAULT_PACKS if p in packs), *v["能力"], *extra])
        v["能力"] = cap_final[n]
    return {"ok": True, "errors": [], "split": {
        "模板": tpl, "角色": roles, "角色模板": "private" if roles else "", "层": order, "层说明": layer_desc, "全局约束": glob,
        "关闭注册": "是" if str(obj.get("关闭注册") or "").strip() in ("是", "true", "True", "1") else "",
        "规则表": rules_all, "模块": norm}}


LAYERS_ORDER = ALL_LAYERS


def layers_md(top, split):
    L_ = ["# 层次 × 模块（LAYERS）", "", f"模板 {split['模板']}；角色 {('、'.join(split['角色']) or '无')}", "", "## 层次", "", "| 层 | 职责 | 目录 |", "|---|---|---|"]
    where = {"能力": "verbs/", "数据": "entities/<模块>.entity", "查询": "queries/<模块>_*.sql", "流程": "scripts/<名>.zs", "接口": "routes/<模块>.zs", "界面": "ui/<页>.ui"}
    L_ += [f"| {k} | {split['层说明'].get(k, '')} | {where[k]} |" for k in split["层"]]
    L_ += ["", "调用方向：界面 → 接口 → 流程 → 查询 → 数据；能力层任何层可用；不许往上调。", "", "## 模块 × 层", "",
           "| 模块 | 依赖 | 数据 | 查询 | 流程 | 接口 | 界面 | 能力 |", "|---|---|---|---|---|---|---|---|"]
    for n in top["构建顺序"]:
        v = split["模块"][n]
        L_.append(f"| {n} | {'、'.join(v['依赖']) or '—'} | {'、'.join(v['数据']) or '—'} | {n}_*.sql | {'、'.join(f['名'] for f in v['流程']) or '—'} | "
                  f"{'、'.join(f['文件'] for f in v['接口']) or '—'} | {'、'.join(f['名'] for f in v['界面']) or '—'} | {'、'.join(v['能力'])} |")
    L_ += ["", "## 各模块规则与缺口", ""]
    for n in top["构建顺序"]:
        v = split["模块"][n]
        L_.append(f"### {n}")
        L_ += [f"- {h}：{t}" for h, t in zip(v["规则号"], v["规则"])] or ["- 规则：无"]
        L_ += [f"- 缺口：{g['事']} → {g['办法']}" + (f"（用 {'、'.join(g['用动词'])}）" if g["用动词"] else "") for g in v["缺口"]]
        L_.append("")
    L_ += ["## 全局约束", ""]
    L_ += [f"- {c}" for c in [*top["横切"]["全局约束"], *split["全局约束"]]] or ["- （无）"]
    L_.append("")
    return "\n".join(L_)


# ================================================================== zs 静态检查

def check_zs(text, rel, vpack, packs, route):
    """DSL 静态检查：块配对、用包真实存在、动词必须在能力清单里（未知动词会静默透传成字面字符串）、动词所属的包要 用包。返回问题列表。"""
    errs, stack, file_packs, cur = [], [], set(), None
    uses = []
    api_seen = False

    def scope():
        return file_packs | (cur or set())

    for i, raw in enumerate(text.splitlines(), 1):
        line = normalize(raw).strip()
        if not line or line.startswith("#") or line[0] in '{}[]",':
            continue
        if route and raw.startswith("接口 ") and not stack:
            stack.append("api")
            cur = set()
            api_seen = True
            continue
        h, rest = split_head(line)
        if h == "use":
            ps = rest.split()
            if not ps:
                errs.append(f"{rel} 第 {i} 行：用包 后面要写包名")
            for p in ps:
                if p not in packs:
                    errs.append(f"{rel} 第 {i} 行：包「{p}」不存在（现有：{sorted(packs)}）")
            (cur if stack and cur is not None else file_packs).update(ps)
        elif h == "set":
            rhs = rest.partition("=")[2].strip()
            if rhs:
                hh, _ = split_head(rhs)
                toks = rhs.split()
                w = toks[0]
                if hh not in HEAD_OK and not re.match(r'[{"\[\-\d]', w) and (len(toks) >= 2 or w in vpack):
                    uses.append((w, i, scope()))
        elif h in HEAD_OK:
            if h in ("if", "each", "foreach", "tx", "while", "repeat"):
                stack.append(h)
            elif h in ("elif", "else"):
                if not stack or stack[-1] != "if":
                    errs.append(f"{rel} 第 {i} 行：「{line.split()[0]}」前面没有对应的 如果")
            elif h == "end":
                if not stack:
                    errs.append(f"{rel} 第 {i} 行：多余的「结束」")
                else:
                    if stack.pop() == "api":
                        cur = None
        else:
            uses.append((h, i, scope()))
    if stack:
        errs.append(f"{rel}：有 {len(stack)} 个块没有「结束」配对（{'、'.join(stack)}）")
    if not file_packs and not api_seen:
        errs.append(f"{rel}：第一行有效语句要是 用包 …")
    for verb, ln, sc in uses:
        if verb not in vpack:
            errs.append(f"{rel} 第 {ln} 行：动词「{verb}」不在能力清单里（未知动词会静默透传成字面字符串，别发明；做不到的事换 sql / 流程）")
        elif vpack[verb] not in sc:
            errs.append(f"{rel} 第 {ln} 行：动词「{verb}」属于包 {vpack[verb]}，但这里没写 用包 {vpack[verb]}")
    return errs


def zs_calls(text):
    """文本里的 执行 / 后台执行 调用：[(行号, 后台?, scripts 路径, {键: 值}, 原行)]。"""
    out = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = CALL_RE.match(line)
        if m:
            out.append((i, m.group(1) == "后台执行", m.group(2), dict(KV_RE.findall(m.group(3) or "")), line))
    return out


def check_calls(text, rel, flowinfo, accessible, on_disk=()):
    """调用的 scripts 存在、入参对得上（必给的都给了，没有多给）、只调 accessible（本模块 / 顶层规定的共用流程）。flowinfo：{流程名: {入参, 可选入参, …}}。"""
    errs = []
    for ln, bg, path, kv, _line in zs_calls(text):
        name = Path(path).stem
        kv = dict(kv)
        on_err = kv.pop("on_error", None) if bg else None
        if on_err is not None:
            en = Path(on_err.removeprefix("{").removesuffix("}")).stem
            if en not in flowinfo and f"scripts/{en}.zs" not in on_disk:
                errs.append(f"{rel} 第 {ln} 行：on_error 指向的 {on_err} 不存在（先建好那个失败处理脚本）")
        if name not in flowinfo:
            errs.append(f"{rel} 第 {ln} 行：调用的 {path} 不存在（已建好的流程：{sorted(flowinfo)}）")
            continue
        if name not in accessible:
            errs.append(f"{rel} 第 {ln} 行：{path} 属于别的模块，本模块不能调（可调：{sorted(accessible)}）")
            continue
        fi = flowinfo[name]
        need, opt = set(fi["入参"]), set(fi.get("可选入参") or [])
        miss = sorted(need - set(kv))
        extra = sorted(set(kv) - need - opt)
        if miss:
            errs.append(f"{rel} 第 {ln} 行：调用 {path} 缺少入参 {'、'.join(miss)}（它的入参 {sorted(need)}，可选 {sorted(opt)}）")
        if extra:
            errs.append(f"{rel} 第 {ln} 行：调用 {path} 多给了它没声明的键 {'、'.join(extra)}（入参 {sorted(need)}，可选 {sorted(opt)}）")
    return errs


def check_sql_scope(text, rel, allowed):
    """zs 里引用的 sql 只能来自 allowed（本模块 + 依赖模块 + gen 自带）。"""
    errs = []
    for i, raw in enumerate(text.splitlines(), 1):
        m = P.CALL.match(raw.strip())
        if m:
            n = m.group(3).removesuffix(".sql")
            if n not in allowed:
                errs.append(f"{rel} 第 {i} 行：sql「{n}」不在本模块和依赖模块的 sql 里（可用：{sorted(allowed)[:40]}）")
    return errs


_FILTER_KW = {"WHERE", "ON", "HAVING"}
_NONFILTER_KW = {"SELECT", "VALUES", "SET", "LIMIT", "OFFSET", "FROM", "BY", "RETURNING", "INTO", "UPDATE", "DELETE", "INSERT", "JOIN", "UNION"}
_PAREN_KW = {"AND", "OR", "NOT", "IN", "EXISTS", "ANY", "ALL", "WHERE", "ON", "HAVING", "WHEN", "THEN", "ELSE", "CASE", "BETWEEN", "LIKE", "IS", "NULL",
             "SELECT", "VALUES", "SET", "LIMIT", "OFFSET", "FROM", "BY", "AS", "UNION", "JOIN", "RETURNING", "DISTINCT", "INTO"}
_TOKEN = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"|:\w+|\w+|[()]|[^\s\w()]")


def _opt_context(text, at):
    """:p 出现在 at 位置时所处的语句成分：「过滤」（WHERE / ON / HAVING 里的比较，要保护）或别的（INSERT 的 VALUES / SELECT 投影、UPDATE 的 SET、
    LIMIT / OFFSET、函数实参、ORDER / GROUP BY——不要求保护）。从该处往回扫到同层最近的子句关键字；跨出括号时，括号前是函数名就是函数实参。"""
    toks = [(m.start(), m.group(0)) for m in _TOKEN.finditer(text)]
    i = next((k for k, (st, _t) in enumerate(toks) if st == at), None)
    if i is None:
        return "其它"
    depth = 0
    for k in range(i - 1, -1, -1):
        t = toks[k][1]
        if t == ")":
            depth += 1
        elif t == "(":
            if depth:
                depth -= 1
                continue
            prev = toks[k - 1][1] if k else ""
            if re.match(r"[A-Za-z_]\w*$", prev) and prev.upper() not in _PAREN_KW:
                return "函数实参"
            if prev.upper() == "VALUES":
                return "VALUES"
        elif depth == 0:
            u = t.upper()
            if u in _FILTER_KW:
                return "过滤"
            if u in _NONFILTER_KW:
                return u
    return "其它"


def check_optional_sql(name, sql, optional):
    """计划里标了「可选」的 sql 参数：不传或传空串都当不过滤，所以每处**拿它做过滤比较**的地方（WHERE / ON / HAVING 里的 `列 = :p`、`:p = 列`、LIKE、< 等）
    要整体括进 `(:p IS NULL OR :p = '' OR col = :p)` 这样的保护里（也认 COALESCE(:p,'')=''、IFNULL(:p,'')=''、顺序颠倒的写法）。
    INSERT 的 VALUES / SELECT 投影、UPDATE 的 SET 赋值、LIMIT / OFFSET、函数实参（NULLIF(:p,'') 等）、ORDER / GROUP BY 里的可选参数不是过滤，不要求保护。
    规则：去掉保护式本身的两处 :p 后，剩下的每一处过滤里的 :p（真正的比较）必须落在含保护式的同一对括号里。返回问题列表。"""
    errs = []
    text = re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), sql)
    for p in optional:
        col = rf":{re.escape(p)}\b"
        guards = [m for m in re.finditer(
            rf"{col}\s+IS\s+NULL\s+OR\s+{col}\s*=\s*''|{col}\s*=\s*''\s+OR\s+{col}\s+IS\s+NULL"
            rf"|(?:COALESCE|IFNULL)\s*\(\s*{col}\s*,\s*''\s*\)\s*=\s*''", text, re.I)]
        used = [m.start() for m in re.finditer(col, text)]
        guarded = {i for g in guards for i in used if g.start() <= i < g.end()}
        for at in used:
            if at in guarded or _opt_context(text, at) != "过滤":
                continue
            ok = False
            for g in guards:
                lo, hi = _paren_span(text, g.start())
                if lo is not None and lo < at < hi:
                    ok = True
                    break
            if not ok:
                errs.append(f"sql「{name}」的可选参数 :{p} 在 WHERE / ON / HAVING 里用来比较时没有空值保护：不传或传空串都要当不过滤，写成 (:{p} IS NULL OR :{p} = '' OR 列 = :{p})，整体括起来")
                break
    return errs


def _paren_span(text, pos):
    """pos 所在的最内层括号 (开, 闭) 下标；不在括号里返回 (None, None)。"""
    depth, lo = 0, None
    for i in range(pos - 1, -1, -1):
        c = text[i]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                lo = i
                break
            depth -= 1
    if lo is None:
        return None, None
    depth = 0
    for j in range(lo, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return lo, j
    return None, None


def wrap_flow(body, name, decl_in):
    """把流程脚本包成一个「接口」块，复用参数核对（入参当请求体字段）；每行缩进两格避免顶格「结束」被当成块尾。"""
    inner = "\n".join("  " + l for l in body.splitlines())
    return f"接口 POST /flow/{name}\n{inner}\n结束\n", {f"/flow/{name}": list(decl_in)}


# ================================================================== 单文件计划校验

def plan_entities(x, expect, visible, err_prefix=""):
    """expect：本模块要建的实体名；visible：依赖模块里已写好的实体名集合。"""
    o, err = S._obj(x)
    if err:
        return None, [err]
    errs, out, names = [], [], []
    items = o.get("实体")
    if not isinstance(items, list) or not items:
        return None, ["「实体」要是非空列表：[{\"名\":…,\"字段\":[{\"名\",\"类型\",\"说明\"}],\"关联\":[…],\"约束\":[…]}]"]
    for e in items:
        n = e.get("名") if isinstance(e, dict) else None
        if not isinstance(n, str):
            errs.append("实体项要有「名」")
            continue
        names.append(n)
        fs = []
        for f in e.get("字段") or []:
            fn = f.get("名") if isinstance(f, dict) else None
            if not isinstance(fn, str) or not SNAKE.match(fn):
                errs.append(f"实体「{n}」的字段名「{fn}」要是英文小写 snake")
                continue
            if fn == "id":
                errs.append(f"实体「{n}」不要写 id 字段（隐含自增）")
            t = str(f.get("类型") or "").strip()
            if t not in FIELD_TYPES:
                errs.append(f"实体「{n}」字段「{fn}」的类型「{t}」只能从 {'/'.join(FIELD_TYPES)} 里选")
            fs.append(fn)
        if not fs:
            errs.append(f"实体「{n}」要有字段")
        rel = _strs(e.get("关联"), f"实体「{n}」的关联", errs)
        for r in rel:
            if r not in expect and r not in visible:
                errs.append(f"实体「{n}」关联的「{r}」不是本模块实体，也不是依赖模块里已写好的实体（可选：{sorted(set(expect) | set(visible))}）")
            elif r == n:
                errs.append(f"实体「{n}」不要关联自己")
            elif f"{r}_id" not in fs:
                errs.append(f"实体「{n}」关联了「{r}」，要有字段 {r}_id")
        out.append({"名": n, "字段": fs, "关联": rel, "约束": _strs(e.get("约束"), f"实体「{n}」的约束", errs)})
    if sorted(names) != sorted(expect) or len(set(names)) != len(names):
        errs.append(f"计划的实体要恰好是 {sorted(expect)}，现在是 {names}")
    return {"实体": out}, errs


def plan_sqls(x, mod, rule_nums, taken, gen_names):
    o, err = S._obj(x)
    if err:
        return None, [err]
    errs, out, seen = [], [], set()
    ss = o.get("sql")
    if ss in (None, ""):
        ss = []
    if not isinstance(ss, list):
        return None, ["「sql」要是列表（不需要定制 sql 就写 []）"]
    for s in ss:
        n = s.get("名") if isinstance(s, dict) else None
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"sql 名「{n}」要是英文小写 snake")
            continue
        if not n.startswith(mod + "_"):
            errs.append(f"sql 名「{n}」要以「{mod}_」开头")
        if n in gen_names:
            errs.append(f"sql 名「{n}」与 gen 自动生成的重名（<实体>_list/one/insert/update/delete 不用写）")
        elif n in taken:
            errs.append(f"sql 名「{n}」项目里已经有了，换个名字")
        if n in seen:
            errs.append(f"sql 名「{n}」重复")
        seen.add(n)
        ps = _strs(s.get("参数"), f"sql「{n}」的参数", errs)
        for p in ps:
            if not IDENT.match(p):
                errs.append(f"sql「{n}」的参数「{p}」不是合法名字")
        os_ = _strs(s.get("可选参数"), f"sql「{n}」的可选参数", errs)
        for p in os_:
            if p not in ps:
                errs.append(f"sql「{n}」的可选参数「{p}」要先列在「参数」里（可选参数是参数的子集）")
        rs = _strs(s.get("规则"), f"sql「{n}」的规则", errs)
        for h in rs:
            if h not in rule_nums:
                errs.append(f"sql「{n}」的规则「{h}」不是分给本模块的规则 {sorted(rule_nums)}")
        out.append({"名": n, "参数": ps, "可选参数": os_, "说明": str(s.get("说明") or ""), "规则": rs})
    return {"sql": out}, errs


def plan_flow(x, rule_nums, sqls, flows, verbs, declared):
    """sqls：可用 sql 名；flows：可调的已建好流程名；verbs：允许的动词名；declared：层次×模块里写的「调流程」。"""
    o, err = S._obj(x)
    if err:
        return None, [err]
    errs = []
    ins = _strs(o.get("入参"), "「入参」", errs)
    opt = _strs(o.get("可选入参"), "「可选入参」", errs)
    outs = _strs(o.get("出参"), "「出参」", errs)
    for p in [*ins, *opt, *outs]:
        if not IDENT.match(p):
            errs.append(f"名字「{p}」不合法（入参 / 出参 要是英文标识符）")
    if set(ins) & set(opt):
        errs.append("入参和可选入参不能重名")
    if not outs:
        errs.append("「出参」不能空：流程要返回点什么，接口才能用 {result.键}")
    us = _strs(o.get("用sql"), "「用sql」", errs)
    for s in us:
        if s not in sqls:
            errs.append(f"用sql「{s}」不存在：只能选已有的 sql {sorted(sqls)[:40]}")
    uf = _strs(o.get("用流程"), "「用流程」", errs)
    for f in uf:
        if f not in flows:
            errs.append(f"用流程「{f}」不能用：只能选已建好的、本模块可调的流程 {sorted(flows)}")
    for f in declared:
        if f not in uf:
            errs.append(f"层次×模块里这个流程要调「{f}」，「用流程」里要写上")
    uv = _strs(o.get("用动词"), "「用动词」", errs)
    for v in uv:
        if v not in verbs:
            errs.append(f"用动词「{v}」不在能力清单里（不许编造）；可用：{sorted(verbs)[:60]}")
    rs = _strs(o.get("规则"), "「规则」", errs)
    for h in rs:
        if h not in rule_nums:
            errs.append(f"规则「{h}」不是分给本模块的规则 {sorted(rule_nums)}")
    steps = _strs(o.get("步骤"), "「步骤」", errs)
    if not steps:
        errs.append("「步骤」要写几条")
    return {"入参": ins, "可选入参": opt, "出参": outs, "用sql": us, "用流程": uf, "用动词": uv, "规则": rs, "步骤": steps}, errs


def plan_ifaces(x, roles, rule_nums, taken_paths, taken_acts, sqls, flows, must_flows):
    """flows：{可调流程名: {入参, 可选入参}}；must_flows：层次×模块里标了「用于」本文件的流程（要在某个接口的用流程里出现）。"""
    o, err = S._obj(x)
    if err:
        return None, [err]
    errs = []
    its = o.get("接口")
    if not isinstance(its, list) or not its:
        return None, ["「接口」要是非空列表，每项 {路径, 动作, 角色, 入参, 用sql, 用流程, 调用, 规则, 说明}"]
    paths, acts, out, usedf = set(), set(), [], set()
    for a in its:
        if not isinstance(a, dict):
            errs.append("接口项要是对象")
            continue
        p, an = a.get("路径"), a.get("动作")
        if not isinstance(p, str) or not p.startswith("/"):
            errs.append(f"接口路径「{p}」要以 / 开头")
        elif p in taken_paths or p in paths:
            errs.append(f"接口路径「{p}」已被占用")
        paths.add(p)
        if not isinstance(an, str) or not SNAKE.match(an):
            errs.append(f"接口「{p}」的动作名「{an}」要是英文小写 snake")
        elif an in taken_acts or an in acts:
            errs.append(f"动作名「{an}」已被占用，换一个")
        acts.add(an)
        ar = a.get("角色") or ""
        if ar and (not isinstance(ar, str) or ar not in roles):
            errs.append(f"接口「{p}」的角色「{ar}」不在项目角色 {roles or '（没有角色）'} 里")
        ins = a.get("入参")
        if not isinstance(ins, list) or not all(isinstance(i, str) and IDENT.match(i) for i in ins):
            errs.append(f"接口「{p}」要有「入参」：请求体字段名列表（没有就写 []）")
            ins = []
        opts = _strs(a.get("可选入参"), f"接口「{p}」的可选入参", errs)
        for o in opts:
            if o not in ins:
                errs.append(f"接口「{p}」的可选入参「{o}」要先列在「入参」里（可选入参是入参的子集）")
        us = _strs(a.get("用sql"), f"接口「{p}」的用sql", errs)
        for s in us:
            if s not in sqls:
                errs.append(f"接口「{p}」的用sql「{s}」不存在：只能用 {sorted(sqls)[:40]}")
        uf = _strs(a.get("用流程"), f"接口「{p}」的用流程", errs)
        calls = a.get("调用") or {}
        if not isinstance(calls, dict):
            errs.append(f"接口「{p}」的调用要是 {{流程名: [键…]}}")
            calls = {}
        for f in uf:
            if f not in flows:
                errs.append(f"接口「{p}」的用流程「{f}」不能用：只能选已建好的、本文件可调的 {sorted(flows)}")
                continue
            ks = calls.get(f)
            if not isinstance(ks, list):
                errs.append(f"接口「{p}」的调用里要写 {f} 的键列表（它的入参 {flows[f]['入参']}）")
                continue
            miss = sorted(set(flows[f]["入参"]) - set(ks))
            extra = sorted(set(ks) - set(flows[f]["入参"]) - set(flows[f].get("可选入参") or []))
            if miss:
                errs.append(f"接口「{p}」调用 {f} 缺入参 {miss}")
            if extra:
                errs.append(f"接口「{p}」调用 {f} 多给了它没声明的键 {extra}")
        for f in calls:
            if f not in uf:
                errs.append(f"接口「{p}」的调用里有「{f}」，但「用流程」没写它")
        usedf |= set(uf)
        rs = _strs(a.get("规则"), f"接口「{p}」的规则", errs)
        for h in rs:
            if h not in rule_nums:
                errs.append(f"接口「{p}」的规则「{h}」不是分给本模块的规则 {sorted(rule_nums)}")
        out.append({"路径": p, "动作": an, "角色": ar, "入参": ins, "可选入参": opts, "用sql": us, "用流程": uf, "调用": {k: list(v) for k, v in calls.items() if isinstance(v, list)},
                    "规则": rs, "说明": str(a.get("说明") or "")})
    for f in must_flows:
        if f not in usedf:
            errs.append(f"层次×模块规定流程「{f}」给本文件用，但没有接口的「用流程」里写它")
    return {"接口": out}, errs


# ================================================================== 继续构建：还原上次状态

class ResumeError(Exception):
    pass


def _ls(v):
    return [str(x) for x in v] if isinstance(v, list) else []


def norm_fp(key, o):
    """把 calls/ 里还原出的单文件计划规整成 f_query / f_flow / f_iface 存的「产出」形状。"""
    if key == "sql":
        ss = o.get("sql") or []
        return {"sql": [{"名": s["名"], "参数": _ls(s.get("参数")), "可选参数": _ls(s.get("可选参数")), "说明": str(s.get("说明") or ""), "规则": _ls(s.get("规则"))} for s in ss]}
    if key == "入参":
        return {k: _ls(o.get(k)) for k in ("入参", "可选入参", "出参", "用sql", "用流程", "用动词", "规则", "步骤")}
    out = []
    for a in o.get("接口") or []:
        calls = a.get("调用") if isinstance(a.get("调用"), dict) else {}
        out.append({"路径": a["路径"], "动作": a["动作"], "角色": str(a.get("角色") or ""), "入参": _ls(a.get("入参")), "可选入参": _ls(a.get("可选入参")), "用sql": _ls(a.get("用sql")),
                    "用流程": _ls(a.get("用流程")), "调用": {k: _ls(v) for k, v in calls.items()}, "规则": _ls(a.get("规则")), "说明": str(a.get("说明") or "")})
    return {"接口": out}


def strip_blocks(text, paths):
    """去掉文件里 paths 这几个路径的接口块（含结尾的「结束」和块后一个空行）；其它块（gen 的 CRUD 等）原样保留。"""
    lines = text.splitlines(keepends=True)
    drop = set()
    for _m, path, ln0, body in P.blocks(text):
        if path in paths:
            end = (body[-1][0] if body else ln0) + 1
            if end > len(lines) or not lines[end - 1].startswith("结束"):
                end = body[-1][0] if body else ln0
            drop.update(range(ln0 - 1, end))
            if end < len(lines) and not lines[end].strip():
                drop.add(end)
    out = "".join(l for i, l in enumerate(lines) if i not in drop)
    return out.rstrip("\n") + "\n" if out.strip() else ""


def reply_text(out, c):
    """calls/<n>_<tag>.reply.txt 里的模型原始回复（去掉末尾 [stderr] 段）。读不到返回 ""。"""
    f = Path(out) / "calls" / f"{int(c['n']):02d}_{c['tag']}.reply.txt"
    try:
        return f.read_text(encoding="utf-8").split("\n\n[stderr]\n")[0]
    except (OSError, KeyError, ValueError):
        return ""


def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def top_from_text(text, packs, task=""):
    """规划文本 → validate_top 结果：DSL（plan/top.zs 或模型回复）；旧版输出目录里的 JSON（文本或 dict）也读。"""
    if isinstance(text, dict):
        return validate_top(text, packs, task)
    t = PD.unfence(text).strip()
    if t[:1] in ("{", "["):
        return validate_top(t, packs, task)
    try:
        obj = PD.parse_top(t)
    except PD.PlanError as e:
        return {"ok": False, "errors": [str(e)], "top": None}
    return validate_top(obj, packs, task)


def split_from_text(text, top, caps, task=""):
    if isinstance(text, dict):
        return validate_split(text, top, caps, task)
    t = PD.unfence(text).strip()
    if t[:1] in ("{", "["):
        return validate_split(t, top, caps, task)
    try:
        obj = PD.parse_layers(t)
    except PD.PlanError as e:
        return {"ok": False, "errors": [str(e)], "split": None}
    return validate_split(obj, top, caps, task)


def _read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except OSError:
        return None


def read_plan(out, task, caps, v2=None, calls=()):
    """从输出目录读回 (top, split, restored)：规划文件 plan/top.zs、plan/layers.zs（可手改）→ 旧版 top.json / split.json →
    result.json 的 v2.顶层规划 → calls/ 里规划步骤的回复（DSL 或旧版 JSON，取最后一个通过校验的）。读不到的抛 ResumeError。"""
    out = Path(out)
    packs = set(caps)
    restored, top = [], None
    cands = []
    t = _read_text(out / "plan" / "top.zs")
    if t is not None:
        cands.append(("plan/top.zs", t))
    cands += [("top.json", _read_json(out / "top.json")), ("result.json 的 v2.顶层规划", (v2 or {}).get("顶层规划"))]
    plan_err = ""
    for src, obj in cands:
        if isinstance(obj, (dict, str)):
            r = top_from_text(obj, packs, task)
            if r["ok"]:
                top = r["top"]
                if src not in ("plan/top.zs", "top.json"):
                    restored.append(src)
                break
            if src == "plan/top.zs":
                plan_err = "；".join(r["errors"])
    if top is None:
        for c in reversed([c for c in calls if c.get("file") == "顶层规划"]):
            r = top_from_text(reply_text(out, c), packs, task)
            if r["ok"]:
                top = r["top"]
                restored.append(f"calls/ 第 {c['n']} 次回复（顶层规划）")
                break
    if top is None:
        raise ResumeError("顶层规划还原不了（plan/top.zs 读不到或没过校验" + (f"：{plan_err[:200]}" if plan_err else "") + "；也没有 top.json，result.json 里的顶层规划不合格，calls/ 里也没有通过校验的回复）")
    split = None
    mods = {m["名"] for m in top["模块"]}
    t = _read_text(out / "plan" / "layers.zs")
    if t is not None:
        r = split_from_text(t, top, caps, task)
        if r["ok"]:
            split = r["split"]
        else:
            plan_err = "；".join(r["errors"])
    if split is None:
        sj = _read_json(out / "split.json")
        if isinstance(sj, dict) and set(sj.get("模块") or {}) == mods and sj.get("规则表") is not None:
            split = sj
    if split is None:
        for c in reversed([c for c in calls if c.get("file") == "层次×模块"]):
            r = split_from_text(reply_text(out, c), top, caps, task)
            if r["ok"]:
                split = r["split"]
                restored.append(f"calls/ 第 {c['n']} 次回复（层次×模块）")
                break
    if split is None:
        raise ResumeError("层次×模块还原不了（plan/layers.zs 读不到或没过校验" + (f"：{plan_err[:200]}" if plan_err else "") + "；也没有 split.json，calls/ 里也没有能通过校验的「层次×模块」回复）")
    return top, split, restored


def restore_state(out_dir, task, caps=None, write=True):
    """从上次的输出目录还原继续构建要的状态：{top, split, files, calls, runs, run_no, n0, prior_cost, restored, contract, frozen}；还原不了抛 ResumeError。
    规划：plan/top.zs、plan/layers.zs（人可以手改后再继续）→ 旧版 top.json / split.json → result.json 的 v2.顶层规划 → calls/ 里规划步骤的回复；
    还原出来的（老版本没有规划文件的产物）会补写 plan/top.zs、plan/layers.zs 到 out（write=False 不写）。
    约定：contracts_frozen.json（骨架的约定部分快照）；contracts.json 只是生成的只读产物，不读。"""
    out = Path(out_dir)
    res = _read_json(out / "result.json")
    if not isinstance(res, dict) or not isinstance(res.get("v2"), dict):
        raise ResumeError(f"{out}/result.json 读不到或不是 newproj 的结果，无法继续构建")
    v2 = res["v2"]
    if not v2.get("modular"):
        raise ResumeError("上次不是 --modular 运行，无法继续构建")
    caps = caps if caps is not None else capabilities()
    calls = _read_json(out / "calls.json")
    calls = calls if isinstance(calls, list) else []
    top, split, restored = read_plan(out, task, caps, v2, calls)
    if write and not (out / "plan" / "top.zs").is_file():
        (out / "plan").mkdir(parents=True, exist_ok=True)
        (out / "plan" / "top.zs").write_text(PD.render_top(top), encoding="utf-8")
    if write and not (out / "plan" / "layers.zs").is_file():
        (out / "plan").mkdir(parents=True, exist_ok=True)
        (out / "plan" / "layers.zs").write_text(PD.render_layers(split), encoding="utf-8")
    files = [r for r in (v2.get("文件") or []) if isinstance(r, dict) and r.get("文件")]
    runs = v2.get("运行")
    if not isinstance(runs, list) or not runs:      # 老结果没有逐次记录：把上次整个当第 1 次
        runs = [{"序号": 1, "结论": v2.get("结论", ""), "状态": res.get("status", ""), "原因": str(res.get("stop") or "")[:400], "花费": float(res.get("cost") or 0),
                 "调用": int(res.get("calls") or 0), "秒": res.get("seconds"), "文件": files}]
    for c in calls:
        c.setdefault("run", 1)
    ns = [int(c["n"]) for c in calls if str(c.get("n", "")).isdigit()]
    ns += [int(f.name.split("_", 1)[0]) for f in (out / "calls").glob("*_*.txt") if f.name.split("_", 1)[0].isdigit()]
    fz = _read_json(out / "contracts_frozen.json")
    return {"top": top, "split": split, "files": files, "calls": calls, "runs": runs, "run_no": max(int(r.get("序号") or 0) for r in runs) + 1,
            "n0": max(ns, default=0), "prior_cost": round(sum(float(r.get("花费") or 0) for r in runs), 4), "restored": restored,
            "contract": bool(v2.get("contract")), "frozen": fz if isinstance(fz, dict) else {}}


def load_plan(old_dir, task, caps=None):
    """--from-plan：读回旧运行的规划（plan/top.zs、plan/layers.zs；旧版 JSON 的 top.json / split.json；再不行按 restore_state 的还原法从 result.json 与 calls/ 里还原），
    新目录里跳过这两步从数据层做起（旧目录是 JSON 规划的，新目录写成 DSL 规划文件）。返回 {top, split, from, restored}；读不到抛 ResumeError。旧目录只读。"""
    out = Path(old_dir)
    if not out.is_dir():
        raise ResumeError(f"{out} 不是目录")
    caps = caps if caps is not None else capabilities()
    v2 = (_read_json(out / "result.json") or {}).get("v2") if isinstance(_read_json(out / "result.json"), dict) else None
    calls = _read_json(out / "calls.json")
    top, split, restored = read_plan(out, task, caps, v2, calls if isinstance(calls, list) else [])
    return {"top": top, "split": split, "from": str(out), "restored": restored or ["plan/top.zs / plan/layers.zs" if (out / "plan" / "top.zs").is_file() else "top.json / split.json"]}


# ================================================================== 3 逐层构建

class ModRun(LY.Run):
    STEP_OF_KIND = {"plan": "mplan", "contract": "mplan", "gen": "mgen", "fallback": "mgen_fallback"}       # DSLAGENT_MODELS 的步骤键：规划类 / 生成类调用分开指定（没写走 sub）；mgen_fallback = mgen 两次都没过检查时再生成 1 次用的模型（没写 = 不回退）
    RETRY_SILENT = (G.R_IDLE, G.R_FIRST)           # 空闲超时 / 首字前静默：同一调用重试 1 次再判失败（输出超长、被杀、熔断不重试）

    in_fallback = False                  # gen_loop 的回退那一次：生成类调用改走 mgen_fallback，并在 calls.json 里标 fallback

    def ask(self, prompt, rec=None, kind="gen"):
        if kind == "gen" and self.in_fallback:
            kind = "fallback"
        return super().ask(prompt, rec, kind)

    def call_limits(self, kind):
        return G.contract_limits() if kind == "contract" else None       # 约定步骤的空闲 / 总超时单独放宽（DSLAGENT_CONTRACT_IDLE / DSLAGENT_CONTRACT_TOTAL 可配）

    def log_mark(self):
        return {"fallback": 1} if self.in_fallback else None

    def fallback_spec(self):
        return (getattr(self.M, "routes", None) or {}).get("mgen_fallback")

    def gen_loop(self, rec, attempt):
        """生成最多 2 次（同 layered）；配了 mgen_fallback 且两次都没过检查，再用回退模型生成 1 次（带前两次的报错）。不配 = 行为不变。"""
        errs = []
        err = rec.get("上次失败") or "无"
        for k in (1, 2):
            rec["生成尝试"] = k
            rec["重写"] = k - 1
            try:
                why = attempt(err)
            except _Retry as e:
                err = str(e)
                errs.append(err)
                continue
            if why is None:
                rec["结果"] = "通过"
                return
            err = why
            errs.append(why)
        fb = self.fallback_spec()
        if not fb:
            raise FileFail(err[:600])
        rec["生成尝试"], rec["重写"], rec["回退"] = 3, 2, fb
        self.bump(1)
        self.in_fallback = True
        try:
            why = attempt("前两次生成都没过检查，报错依次是：" + "；".join(f"({i}) {x}" for i, x in enumerate(errs, 1)))
        except _Retry as e:
            why = str(e)
        finally:
            self.in_fallback = False
        if why is None:
            rec["结果"] = "通过"
            return
        raise FileFail(f"回退模型也没过：{why}"[:600])

    def __init__(self, M, task, project, stop_cls, cap=None, out_dir=None, verbs_root=None, resume=None, codex_cap=None, contract=False, from_plan=None):
        super().__init__(M, task, project, stop_cls, cap)
        self.codex_cap = codex_cap
        self.contract_on = bool(resume["contract"]) if resume else bool(contract)      # 先约定接口再按约定实现；继续构建沿用上次的做法
        self.from_plan = from_plan          # load_plan() 的结果：{top, split}，跳过顶层规划与层次×模块
        self.contracts = {}                 # 模块 → 约定（从骨架提取、validate_contract 规范化后的对象）
        self.skel = {}                      # 模块 → {路径: 规范骨架文本}（程序按约定渲染，给实现步骤当输入、失败时回退用）
        self.frozen = {}                    # 模块 → {路径: 约定部分快照}（冻结；实现的约定部分要与它逐行一致）
        self.loaded_frozen = (resume or {}).get("frozen") or {}
        self.out = Path(out_dir) if out_dir else self.root
        self.resume = resume                # restore_state() 的结果；None = 全新运行
        self.run_no = resume["run_no"] if resume else 1
        self.prev = {r["文件"]: r for r in resume["files"]} if resume else {}      # 上次每个文件的记录
        self.data_changed = False
        self.changed = set()            # 这次运行里被重做过（调了模型）且通过的文件：依赖它的、上次通过的下游文件要重新过检查
        self.trials = {"调用": 0, "不过": 0, "跳过": []}
        self.ui_check = None
        M.run_no = self.run_no
        if resume:
            self.n0 = self.k = M.n0 = M.n = resume["n0"]
            M.log[:0] = resume["calls"]
            M.log_start = len(resume["calls"])
        self.caps = capabilities(verbs_root)
        self.vpack = verb_packs(self.caps)
        self.pm = {n: _prompt(f"sys_m{n}.md") for n in ("top", "split", "contract", "plan_ent", "plan_sql", "plan_flow", "plan_iface", "plan_ui",
                                                         "gen_ent", "gen_sql", "gen_flow", "gen_iface", "gen_ui")}
        self.top = self.split = None
        self.deps = {}
        self.msql = {}                  # 模块 → {sql名: [参数]}（本模块定制 sql）
        self.flowinfo = {}              # 流程名 → {模块, 入参, 可选入参, 出参, 用sql, 文件}
        self.claimed = {}               # 规则号 → [claim 它的文件]
        self.expected = []              # 层次×模块定下来的全部文件项（按构建顺序）
        self.plan_tops, self.plan_split = [], []

    def system(self):
        return _prompt("sys_mmodel.md")

    # ------------------------------------------------------------ 上下文
    def dscope(self, m):
        return {m} | closure(self.deps, m)

    def mod(self, m):
        return self.split["模块"][m]

    def top_view(self):
        t = self.top
        return json.dumps({"目标": t["目标"], "使用者": t["使用者"], "模块": t["模块"], "共用流程": t["共用流程"], "横切": t["横切"], "构建顺序": t["构建顺序"]}, ensure_ascii=False)

    def mod_view(self, m):
        v = self.mod(m)
        return json.dumps({"模块": m, "说明": v["说明"], "依赖模块": v["依赖"], "规则": dict(zip(v["规则号"], v["规则"])), "数据": v["数据"],
                           "流程": v["流程"], "接口": v["接口"], "界面": v["界面"], "缺口": v["缺口"]}, ensure_ascii=False)

    def cap_for(self, m):
        return cap_text(self.caps, set(self.mod(m)["能力"]))

    def ok_ents(self):
        return self.ok_mods("数据")

    def gen(self):
        if not self.ok_ents():
            self.fatal = "没有一个模块的实体写成：" + "；".join(f"{r['文件']}：{r['失败原因']}" for r in self.recs if r["层"] == "数据")[:500]
            return
        g = self.v["生成增删改查"]({"项目目录": ".", "模板": self.layers["模板"], "角色": self.layers["角色"], "关闭注册": "是" if self.no_register() else "否"})
        if g["ok"] != "是":
            self.fatal = f"生成增删改查不过：{g['msg']}"
            return
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            self.fatal = f"gen 生成的项目检查不过：{b['msg']}"

    def no_register(self):
        """要不要关公开注册：顶层规划横切（账号与权限 / 全局约束）、层次×模块的全局约束里写了「学生不能自己注册、由教师建」，或清单带标记 关闭注册＝是。"""
        if str((self.split or {}).get("关闭注册") or "") in ("是", "true", "True", "1"):
            return True
        c = (self.top or {}).get("横切") or {}
        texts = [str(c.get("账号与权限") or ""), *[str(x) for x in c.get("全局约束") or []], *[str(x) for x in (self.split or {}).get("全局约束") or []]]
        return bool(self.layers["角色"]) and any(NO_REGISTER_RE.search(t) for t in texts)

    def reapply_perms(self):
        """对磁盘上已有的 gen 产物重新套权限（resume / 模型追加过接口之后）：只改 gen 生成的增删改查块，保留追加部分。可重复。"""
        if self.layers["模板"] != "private" or self.fatal:
            return
        g = self.v["生成增删改查"]({"项目目录": ".", "模板": "private", "角色": self.layers["角色"], "只套权限": "是", "关闭注册": "是" if self.no_register() else "否"})
        if g["ok"] != "是":
            self.fatal = f"套 gen 权限不过：{g['msg']}"

    def gen_ents(self):
        """gen 生成的实体文件（entities/ 里不属于任何业务模块的，如 private 的 user）全文。"""
        d = self.root / "entities"
        mods = {m["名"] for m in self.top["模块"]}
        fs = [f for f in sorted(d.glob("*.entity")) if f.stem not in mods] if d.is_dir() else []
        return "\n\n".join(f.read_text(encoding="utf-8").strip() for f in fs), [f.stem for f in fs]

    def ents_with_gen(self, names):
        """业务实体全文 + gen 生成的实体全文（含真实表名 / 列名）。查询 / 流程 / 接口的规划与生成输入都用它。"""
        text = self.ent_text(names)
        gen, stems = self.gen_ents()
        if not gen:
            return text
        acc = [x for x in stems if x in ACCOUNT_ENTS]
        note = (f"账号表是 {acc[0]}（gen 生成）；" if acc else "") + "它们不属于任何业务模块、所有模块都能直接用；表名就是实体名，列名以实体里的「字段」为准（另有隐含 id）"
        return f"{text or '（无）'}\n\ngen 生成的实体全文（{note}）：\n{gen}"

    def ok_mods(self, layer):
        return {r["模块"] for r in self.recs if r["层"] == layer and r["结果"] == "通过"}

    def visible_ents(self, m):
        """依赖范围内已写好的实体名（真实实体名，不是模块名）。"""
        ok = self.ok_mods("数据")
        return [e for d in sorted(self.dscope(m) & ok) for e in self.mod(d)["数据"]]

    def visible_sqls(self, m):
        """可用的 sql：本模块 / 依赖模块的定制 sql ＋ gen 为可见实体生成的（磁盘上真有的）。"""
        out = {}
        for d in self.dscope(m):
            out.update(self.msql.get(d, {}))
        gen = L.gen_sqls(self.visible_ents(m))
        disk = self.disk_sqls()
        out.update({s: disk[s] for s in gen if s in disk})
        return out

    def accessible_flows(self, m):
        """m 能调的流程：本模块的 ＋ 顶层「共用流程」规定给 m 用的；只含已建好的。"""
        out = {n: i for n, i in self.flowinfo.items() if i["模块"] == m}
        for s in self.top["共用流程"]:
            if m in s["被用于"] and s["流程名"] in self.flowinfo:
                out[s["流程名"]] = self.flowinfo[s["流程名"]]
        return out

    def sig_text(self, sqls, own):
        """依赖模块的 sql 只给名字 / 参数；本模块的另给全文。"""
        return "；".join(f"{s}({','.join(p)})" for s, p in sqls.items() if s not in own) or "（无）"

    def rule_view(self, nums):
        return json.dumps(self.rule_texts_m(nums), ensure_ascii=False)

    def rule_texts_m(self, nums):
        t = self.split["规则表"]
        return [f"{h}：{t[h]}" for h in nums if h in t]

    def claim(self, nums, file):
        for h in nums:
            self.claimed.setdefault(h, []).append(file)

    # ------------------------------------------------------------ 记录
    def mrec(self, layer, file, m, deps=()):
        rec = self.new(layer, file, m, deps)
        rec["模块"] = m
        rec["运行"] = self.run_no
        return rec

    def run_file(self, layer, file, m, deps, fn, *a):
        old = self.prev.get(file)
        note = ""
        ups = [d for d in deps if d in self.changed]            # 这次被重做过的上游
        if old and old["结果"] == "通过" and not self.bad_deps({"依赖": deps}):
            note = self.try_carry(layer, file, m, old, a[0] if a else None, ups)
            if not note:
                if ups:
                    self.state[file]["上游变化复查"] = "通过（上游 " + "、".join(ups) + " 重做过）"
                return self.state[file]
            self.bump(4 if layer in ("数据", "查询", "界面") else 8)
            self.discard_stale(layer, file, old)
            note = f"因上游变化重做：{note}（上游 {'、'.join(ups)} 这次重做过）" if ups else f"上次通过，这次不能沿用：{note}"
        rec = self.mrec(layer, file, m, deps)
        if ups and note:
            rec["因上游变化重做"] = True
        if old and old["结果"] == "失败" and old.get("失败原因"):
            rec["上次失败"] = f"上次运行失败：{old['失败原因']}"
        elif old and old["结果"] == "跳过":
            rec["排回待做"] = True
            rec["上次失败"] = f"上次因依赖没写成而跳过（{old.get('失败原因', '')}），这次依赖已通过，排回重做"
        elif note:
            rec["上次失败"] = note
        bad = self.bad_deps(rec)
        if bad:
            rec.update(结果="跳过", 失败原因="依赖的文件没写成：" + "、".join(bad))
            return rec
        try:
            fn(rec, *a)
        except FileFail as e:
            rec.update(结果="失败", 失败原因=str(e)[:600])
        if layer == "数据" and rec["结果"] == "通过":
            self.data_changed = True
        if rec["结果"] == "通过":
            self.changed.add(file)
        return rec

    def requeue_skipped(self):
        """同一次运行内：之前因依赖失败被「跳过」的文件，只要它依赖的文件现在都通过了，就排回重做（记录里标「排回待做」，替换掉原来的跳过记录）。"""
        fns = {"数据": self.f_entity, "查询": self.f_query, "流程": self.f_flow, "接口": self.f_iface, "界面": self.f_ui}
        again = True
        while again:
            again = False
            for it in self.expected:
                r = self.state.get(it["文件"])
                if it["层"] == "约定" or r is None or r["结果"] != "跳过" or self.bad_deps(r) or any(self.state.get(d) is None and d in {x["文件"] for x in self.expected} for d in r["依赖"]):
                    continue
                self.recs.remove(r)
                self.state.pop(it["文件"], None)
                self.bump(4 if it["层"] in ("数据", "查询", "界面") else 8)
                rec = self.run_file(it["层"], it["文件"], it["模块"], it["依赖"], fns[it["层"]], it)
                rec["排回待做"] = True
                again = True

    # ------------------------------------------------------------ 继续构建：沿用上次通过的文件
    def try_carry(self, layer, file, m, old, it, ups=()):
        """上次通过的文件：仍在磁盘、仍过检查就沿用（把上次记录原样放回、还原内存里的 sql / 流程 / 接口状态），返回 None；不能沿用返回原因。"""
        p = self.root / file
        fp = None
        if layer == "查询":
            fp = self.contract_plan(layer, it) if self.contract_on else old.get("产出") or self.replay_plan(file, "sql")
            if fp is None:
                return "上次的 sql 计划还原不了"
            names = [s["名"] for s in fp["sql"]]
            miss = [n for n in names if not (self.root / "queries" / f"{n}.sql").is_file()]
            if miss:
                return f"sql 文件不在磁盘：{miss}"
            if names and self.contract_on:
                fe = [e for n in names for e in self.frozen_errs(m, f"queries/{n}.sql", (self.root / "queries" / f"{n}.sql").read_text(encoding="utf-8"))]
                if fe:
                    return "；".join(fe)[:400]
            if names:
                blk = {"ok": "是", "files": [{"file": f"queries/{n}.sql", "content": (self.root / "queries" / f"{n}.sql").read_text(encoding="utf-8")} for n in names]}
                c = self.v["预编译sql"](blk, self.ent_text())
                if c["ok"] != "是":
                    return "预编译不过：" + str(c["msg"])[:300]
        elif not p.is_file():
            return "文件不在磁盘"
        elif layer == "数据":
            from tools.entity import parse
            try:
                names = [x.name for x in parse(p.read_text(encoding="utf-8"))]
            except Exception as ex:  # noqa: BLE001
                return f"实体解析失败：{ex}"
            if sorted(names) != sorted(self.mod(m)["数据"]):
                return f"实体 {names} 与计划 {self.mod(m)['数据']} 不符"
        elif layer == "流程":
            fp = self.contract_plan(layer, it) if self.contract_on else old.get("产出") or self.replay_plan(file, "入参")
            if fp is None:
                return "上次的流程计划还原不了"
            name = it["流程"]
            body = p.read_text(encoding="utf-8")
            flows, sqls = self.accessible_flows(m), self.visible_sqls(m)
            errs = check_zs(body, file, self.vpack, set(self.caps), False) + LC.check_text(body, file, False)
            if not errs:
                wrapped, decl = wrap_flow(body, name, [*fp["入参"], *fp["可选入参"]])
                with self.qdir() as qd:
                    errs += P.check_text(wrapped, file, qd, decl, P.identity_vars(self.root))[0]
                errs += check_calls(body, file, self.flowinfo, set(flows), self.disk_scripts())
                errs += check_sql_scope(body, file, set(sqls))
                if self.contract_on:
                    errs += self.contract_flow_errs(file, body, fp)
            if self.contract_on:
                errs += self.frozen_errs(m, file, body)
            if errs:
                return "；".join(errs)[:400]
            self.flowinfo[name] = {"模块": m, "入参": fp["入参"], "可选入参": fp["可选入参"], "出参": fp["出参"], "用sql": fp["用sql"], "文件": file}
            self.claim(fp["规则"], file)
        elif layer == "接口":
            fp = self.contract_plan(layer, it) if self.contract_on else old.get("产出") or self.replay_plan(file, "接口")
            if fp is None:
                return "上次的接口计划还原不了"
            items = fp["接口"]
            text = p.read_text(encoding="utf-8")
            have = {path for _m, path, _n, _l in P.blocks(text)}
            miss = [a["路径"] for a in items if a["路径"] not in have]
            if miss:
                return f"文件里没有接口块 {miss}"
            body = self.iface_body(text, items)
            errs = check_zs(body, file, self.vpack, set(self.caps), True)
            errs += LC.check_text(body, file, True)
            errs += check_calls(text, file, self.flowinfo, set(self.accessible_flows(m)), self.disk_scripts())
            if ups:                      # 上游重做过：入参核对（sql 参数 / 流程入参可能变了）与 sql 范围也要重过
                with self.qdir() as qd:
                    pe, _ = P.check_text(body, file, qd, {a["路径"]: a["入参"] for a in items}, P.identity_vars(self.root))
                errs += ["参数核对不过：" + x for x in pe]
                errs += check_sql_scope(body, file, set(self.visible_sqls(m)))
            if self.contract_on:
                errs += self.contract_iface_errs(file, body, items)
                errs += self.frozen_errs(m, file, body)
            if ups and not errs:         # 上游重做过：接口再试调一遍
                errs += self.trial({file: items})
            if errs:
                return "；".join(errs)[:400]
            self.ifaces[file] = items
            for a in items:
                self.paths[a["路径"]] = {"动作": a["动作"], "入参": a["入参"], "文件": file, "实体": m, "说明": a["说明"]}
                self.acts.add(a["动作"])
            self.claim(_dedup([h for a in items for h in a["规则"]]), file)
        elif layer == "界面":
            if self.contract_on:
                fe = self.frozen_errs(m, file, p.read_text(encoding="utf-8"))
                if fe:
                    return "；".join(fe)[:400]
            if self.ui_check is None:
                self.ui_check = self.v["检查项目"]({})
            if self.ui_check["ok"] != "是" and file in str(self.ui_check["msg"]):
                return "检查项目不过：" + str(self.ui_check["msg"])[:300]
        if layer == "查询":
            self.msql[m] = {s["名"]: list(s["参数"]) for s in fp["sql"]}
            for s in fp["sql"]:
                self.sql_owner[s["名"]] = file
                self.claim(s["规则"], file)
        rec = dict(old)
        rec["沿用"] = True
        if fp is not None:
            rec["产出"] = fp
        self.recs.append(rec)
        self.state[file] = rec
        return None

    def discard_stale(self, layer, file, old):
        """不能沿用的旧产物先清掉，免得重做时撞名（旧 sql 名被占 / 接口块追加后重复 / 旧流程文件「已存在，不能覆盖」）。数据、界面重做时整个文件覆盖，不用清。"""
        if self.contract_on and layer in ("流程", "查询", "接口"):       # 约定模式：旧实现换回骨架（失败了项目也是完整的，调到就报「未实现」）
            for m, fs in self.skel.items():
                rels = [r for r in fs if (r == file if layer != "查询" else (SK.kind_of(r) == "sql" and file == f"queries/{m}_*.sql"))]
                if rels:
                    self.put_skeleton(m, set(rels))
            return
        if layer == "流程":
            (self.root / file).unlink(missing_ok=True)
        elif layer == "查询":
            fp = old.get("产出") or self.replay_plan(file, "sql")
            for sq in (fp or {}).get("sql", []):
                (self.root / "queries" / f"{sq['名']}.sql").unlink(missing_ok=True)
        elif layer == "接口":
            fp = old.get("产出") or self.replay_plan(file, "接口")
            p = self.root / file
            if fp and p.is_file():
                left = strip_blocks(p.read_text(encoding="utf-8"), {a["路径"] for a in fp["接口"]})
                if left.strip():
                    p.write_text(left, encoding="utf-8", newline="")
                else:
                    p.unlink()

    def replay_plan(self, rel, key):
        """从上次 calls.json + calls/ 里该文件的规划回复还原单文件计划（旧版没把计划落进 result.json）：取最后一个含 key 的 JSON 对象。"""
        got = None
        for c in (self.resume or {}).get("calls", []):
            if c.get("file") != rel:
                continue
            txt = reply_text(self.out, c)
            o, err = S._obj(txt) if txt else (None, "x")
            if err or not isinstance(o, dict) or key not in o:
                continue
            got = o
        if got is None:
            return None
        try:
            return norm_fp(key, got)
        except (TypeError, AttributeError, KeyError):
            return None

    def fplan(self, rec, sysp, body, validate):
        """单文件规划 ≤2 次：校验不过带报错重写；两次不过抛 FileFail。"""
        err = rec.get("上次失败") or "无"
        for k in (1, 2):
            rec["规划尝试"] = k
            try:
                text = self.ask(f"{sysp}\n需求：{self.task}\n{body}\n上次的报错：{err}", rec, "plan")
            except _Retry as e:
                err = str(e)
                continue
            plan, errs = validate(text)
            if not errs:
                return plan
            err = "；".join(errs)
        raise FileFail(f"单文件规划两次没过：{err}"[:600])

    def bump_budget(self):
        n = 0
        for f in self.expected:
            if self.prev.get(f["文件"], {}).get("结果") == "通过":
                continue                # 继续构建：上次通过的先不算预算，不能沿用时再补（run_file）
            n += 2 if f["层"] == "约定" else 4 if f["层"] in ("数据", "查询", "界面") else 8
        self.bump(n)

    # ------------------------------------------------------------ 1 顶层规划
    def make_top(self):
        st = self.step("顶层规划")
        self.bump(2)
        err = "无"
        for k in (1, 2):
            st["尝试"] = k
            try:
                text = self.ask(f"{self.pm['top']}\n需求：{self.task}\n现有动词包（能力清单，只列动词名）：\n{cap_text(self.caps, brief=True)}\n上次的报错：{err}", st, "plan")
            except _Retry as e:
                err = str(e)
                continue
            except FileFail as e:
                self.fatal = f"顶层规划没有完成：{e}"
                return
            try:
                obj = PD.parse_top(text)
            except PD.PlanError as e:
                err = str(e)
                continue
            r = validate_top(obj, set(self.caps), self.task)
            if r["ok"]:
                self.top = r["top"]
                self.deps = top_deps(self.top)
                self.save_plan("top.zs", text)
                (self.out / "PLAN.md").write_text(plan_md(self.top), encoding="utf-8")
                return
            err = "；".join(r["errors"])
        self.fatal = f"顶层规划两次都没过：{err}"[:800]

    def save_plan(self, name, text):
        """规划文件落盘：plan/top.zs、plan/layers.zs（源头；PLAN.md / LAYERS.md 由程序从它们生成）。"""
        d = self.out / "plan"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(PD.unfence(text).strip() + "\n", encoding="utf-8")

    # ------------------------------------------------------------ 2 层次 × 模块
    def make_split(self):
        st = self.step("层次×模块")
        self.bump(2)
        err = "无"
        for k in (1, 2):
            st["尝试"] = k
            try:
                text = self.ask(f"{self.pm['split']}\n需求：{self.task}\n顶层规划：{self.top_view()}\n能力清单（动词名按包分）：\n{cap_text(self.caps, brief=True)}\n上次的报错：{err}", st, "plan")
            except _Retry as e:
                err = str(e)
                continue
            except FileFail as e:
                self.fatal = f"层次×模块没有完成：{e}"
                return
            try:
                obj = PD.parse_layers(text)
            except PD.PlanError as e:
                err = str(e)
                continue
            r = validate_split(obj, self.top, self.caps, self.task)
            if r["ok"]:
                self.split = r["split"]
                self.layers = {"模板": self.split["模板"], "角色": self.split["角色"], "角色模板": self.split["角色模板"],
                               "层": self.split["层"], "规则表": self.split["规则表"]}
                self.save_plan("layers.zs", text)
                (self.out / "LAYERS.md").write_text(layers_md(self.top, self.split), encoding="utf-8")
                self.plan_files()
                return
            err = "；".join(r["errors"])
        self.fatal = f"层次×模块两次都没过：{err}"[:800]

    def plan_files(self):
        """层次×模块定下来的全部文件项；halt 时没建的记「未做」，也用来算调用预算。"""
        ex = []
        ent_file = lambda d: f"entities/{d}.entity"     # noqa: E731
        for layer in BUILD_LAYERS:
            for m in self.top["构建顺序"]:
                v = self.mod(m)
                dep_ents = [ent_file(d) for d in self.deps[m] if self.mod(d)["数据"]]
                if layer == "数据" and v["数据"]:
                    ex.append({"层": layer, "文件": ent_file(m), "模块": m, "依赖": dep_ents})
                if layer == "查询" and (v["流程"] or v["接口"]):
                    ex.append({"层": layer, "文件": f"queries/{m}_*.sql", "模块": m, "依赖": ([ent_file(m)] if v["数据"] else []) + dep_ents})
                if layer == "流程":
                    for f in v["流程"]:
                        ex.append({"层": layer, "文件": f"scripts/{f['名']}.zs", "模块": m, "流程": f["名"],
                                   "依赖": [*([ent_file(m)] if v["数据"] else []), f"queries/{m}_*.sql", *(f"scripts/{c}.zs" for c in f["调流程"])]})
                if layer == "接口":
                    for f in v["接口"]:
                        used = [x["名"] for mm in self.split["模块"].values() for x in mm["流程"] if f["文件"] in x["用于"]]
                        ex.append({"层": layer, "文件": f"routes/{f['文件']}.zs", "模块": m, "接口文件": f["文件"],
                                   "依赖": [*([ent_file(m)] if v["数据"] else []), f"queries/{m}_*.sql", *(f"scripts/{u}.zs" for u in used)]})
                if layer == "界面":
                    for f in v["界面"]:
                        ex.append({"层": layer, "文件": f"ui/{f['名']}.ui", "模块": m, "页": f["名"],
                                   "依赖": [f"routes/{x['文件']}.zs" for x in v["接口"]] or ([ent_file(m)] if v["数据"] else [])})
        if self.contract_on:
            # 约定模式：实现层只照约定写，文件之间互不依赖——只依赖「本模块的实体」和「本模块的约定」，别的文件写没写成都不影响它
            for it in ex:
                m = it["模块"]
                own = [ent_file(m)] if self.mod(m)["数据"] else []
                if it["层"] in ("流程", "接口", "界面"):
                    it["依赖"] = [*own, self.cfile(m)]
                elif it["层"] == "查询":
                    it["依赖"] = [*it["依赖"], self.cfile(m)]
            cs = [{"层": "约定", "文件": self.cfile(m), "模块": m,
                   "依赖": [*([ent_file(m)] if self.mod(m)["数据"] else []), *(ent_file(d) for d in self.deps[m] if self.mod(d)["数据"]), *(self.cfile(d) for d in self.deps[m])]}
                  for m in self.top["构建顺序"]]
            ex = cs + ex
        self.expected = ex
        self.bump_budget()

    # ------------------------------------------------------------ 3 逐层构建
    def build_all(self):
        fns = {"数据": self.layer_data, "查询": self.layer_query, "流程": self.layer_flow, "接口": self.layer_iface, "界面": self.layer_ui}
        for layer in BUILD_LAYERS:
            if self.fatal:
                return
            fns[layer]([f for f in self.expected if f["层"] == layer])
            self.requeue_skipped()
            if layer == "数据":
                if self.need_gen():
                    self.gen()
                self.reapply_perms()
                if self.contract_on and not self.fatal:
                    self.make_contracts()
        if self.contract_on and not self.fatal:
            self.trial_round()

    def need_gen(self):
        """全新运行总要 gen；继续构建时只有数据层有文件重做过、或 gen 的产物不全才再 gen（gen 不覆盖已有文件）。"""
        if not self.resume or self.data_changed:
            return True
        if self.layers["模板"] == "private" and not (self.root / "entities" / "user.entity").is_file():
            return True
        return any(not (self.root / "queries" / f"{e}_list.sql").is_file() for m in self.ok_ents() for e in self.mod(m)["数据"])

    # ------------------------------------------------------------ 接口约定
    @staticmethod
    def cfile(m):
        return f"contracts/{m}.skel"

    def ent_cols(self):
        """磁盘上全部实体 → {名: {列…}}（含隐含 id）。"""
        from tools.entity import parse
        try:
            return {e.name: {f.name for f in e.fields} | {"id"} for e in parse(self.ent_text())}
        except Exception:  # noqa: BLE001
            return {}

    def ents_sql(self):
        from tools.entity import render_sql
        try:
            return render_sql(self.ent_text())
        except Exception:  # noqa: BLE001
            return ""

    def contract_ctx(self, m, own=None):
        """own：本模块自己已有的 {sql, paths, acts}（沿用冻结约定重新校验时，它们在磁盘上已经有了，不算「被占用」）。"""
        own = own or {"sql": set(), "paths": set(), "acts": set()}
        v = self.mod(m)
        scope = self.dscope(m)
        other = {e for mm, vv in self.split["模块"].items() if mm not in scope for e in vv["数据"]}
        ents = {k: c for k, c in self.ent_cols().items() if k not in other}
        disk = self.disk_sqls()
        gen_vis = L.gen_sqls(list(ents))
        sql_known = {s: {"名": s, "参数": [{"名": x, "要求": "必填"} for x in ps]} for s, ps in disk.items() if s in gen_vis}
        for d in scope - {m}:
            for s in (self.contracts.get(d) or {}).get("sql", []):
                sql_known[s["名"]] = s
        flows_ext = {}
        for s in self.top["共用流程"]:
            if m in s["被用于"] and s["归属模块"] != m:
                for f in (self.contracts.get(s["归属模块"]) or {}).get("流程", []):
                    if f["名"] == s["流程名"]:
                        flows_ext[f["名"]] = f
        routes = self.v["项目摘要"]({"含参数": "是"})["routes"]
        gen_paths = {x["path"] for x in routes}
        every = [i for c in self.contracts.values() for i in c["接口"]]
        ui_paths = gen_paths | {i["路径"] for d in scope - {m} for i in (self.contracts.get(d) or {}).get("接口", [])}
        packs = set(v["能力"])
        return {"mod": m, "v": v, "ents": ents, "own_tables": v["数据"], "sql_known": sql_known, "flows_ext": flows_ext,
                "gen_sqls": L.gen_sqls([e for mm in self.split["模块"].values() for e in mm["数据"]]) | gen_vis, "taken_sqls": set(disk) - own["sql"],
                "taken_paths": (gen_paths | {i["路径"] for i in every}) - own["paths"], "taken_acts": ({x["action"] for x in routes if x.get("action")} | {i["动作"] for i in every}) - own["acts"],
                "ui_paths": ui_paths, "verbs": {x["名"] for p in packs for x in self.caps.get(p, [])}, "roles": self.layers["角色"],
                "other_flows": {f["名"] for mm in self.split["模块"].values() for f in mm["流程"]},
                "flow_calls": {f["名"]: {"flows": [c["名"] for c in f["调"] if c.get("类") == "流程"], "sql": [c["名"] for c in f["调"] if c.get("类") == "sql"]}
                              for mm, c in self.contracts.items() if mm != m for f in c["流程"]},
                "must_by_file": {f["文件"]: [fl["名"] for mm in self.split["模块"].values() for fl in mm["流程"] if f["文件"] in fl["用于"]] for f in v["接口"]}}

    def contract_prompt(self, m, ctx, err, part=0, head=""):
        """part：0 = 一次写全；1 = 拆分的第一次（只写 sql + 流程）；2 = 拆分的第二次（只写接口 + 界面，head 是第一次已校验通过的骨架）。"""
        scope = self.dscope(m) - {m}
        deps = "\n".join(f"=== {rel} ===\n{txt.strip()}" for d in sorted(scope) for rel, txt in (self.frozen.get(d) or {}).items()) or "（无）"
        shared = "\n".join(f"=== scripts/{k}.zs ===\n" + "\n".join(SK.flow_head(f)) for k, f in ctx["flows_ext"].items()) or "（无）"
        gen = "；".join(f"{s}({','.join(p['名'] for p in x['参数'])})" for s, x in sorted(ctx["sql_known"].items()) if s in L.gen_sqls(list(ctx["ents"])))
        summary = self.v["项目摘要"]({"含参数": "是"})["text"]
        return (f"{self.pm['contract']}\n需求：{self.task}\n顶层规划：{self.top_view()}\n本模块：{self.mod_view(m)}\n"
                f"本模块与依赖模块的实体全文：{self.ents_with_gen(self.dscope(m)) or '（无）'}\ngen 生成的增删改查 sql（名字参数）：{gen or '（无）'}\n"
                f"项目里已有的接口（gen 的增删改查等，路径不能重复）：{summary}\n依赖模块已冻结的约定（骨架头部，只给签名，参数后带 ? = 可选；不给实现）：\n{deps}\n"
                f"本模块可调的共用流程（骨架头部）：\n{shared}\n接口文件 → 必须调用的流程：{json.dumps(ctx['must_by_file'], ensure_ascii=False)}\n"
                f"本模块要写的流程：{json.dumps([f['名'] for f in self.mod(m)['流程']], ensure_ascii=False)}；接口文件：{json.dumps([f['文件'] for f in self.mod(m)['接口']], ensure_ascii=False)}；界面页：{json.dumps([u['名'] for u in self.mod(m)['界面']], ensure_ascii=False)}\n"
                f"项目角色：{json.dumps(self.layers['角色'], ensure_ascii=False)}\n能力清单（本模块用到的包）：\n{self.cap_for(m)}\n分配的规则：{self.rule_view(self.mod(m)['规则号'])}\n"
                + {0: "", 1: "【拆成两次调用】这一次只输出 queries/*.sql 与 scripts/*.zs 骨架（sql + 流程）；接口 routes/*.zs 与界面 ui/*.ui 下一次再写，现在不要写。\n",
                   2: "【拆成两次调用】sql 与流程骨架已在上一次写好并校验通过（只读，原样不要再输出；接口调用的参数、规则要与它们对得上）：\n" + head
                   + "\n这一次只输出 routes/*.zs 与 ui/*.ui 骨架文件。\n"}[part]
                + f"上次的报错：{err}")

    def action_map(self):
        """接口路径 → 动作名（本项目已约定的 + gen 的增删改查），界面骨架里的远程动作用。"""
        acts = {x["path"]: x["action"] for x in self.v["项目摘要"]({"含参数": "是"})["routes"] if x.get("action")}
        acts.update({i["路径"]: i["动作"] for c in self.contracts.values() for i in c["接口"]})
        return acts

    def skeleton_text(self, rel, m):
        """磁盘上/规范的骨架文本（给实现步骤当输入）：优先取 self.skel（程序按约定渲染的规范骨架）。"""
        return (self.skel.get(m) or {}).get(rel, "")

    def put_skeleton(self, m, rels=None):
        """把 m 的规范骨架写到真实路径上（rels 限定哪几个）。接口文件里 gen 的 CRUD 块原样保留，骨架块追加在后面。返回 [(rel, 之前内容)]。"""
        saved = []
        for rel, text in (self.skel.get(m) or {}).items():
            if rels is not None and rel not in rels:
                continue
            if SK.kind_of(rel) == "route" and (self.root / rel).is_file():
                paths = {a["路径"] for a in self.contracts[m]["接口"] if f"routes/{a['文件']}.zs" == rel}
                base = SK.cut_skeleton_blocks((self.root / rel).read_text(encoding="utf-8"), paths)
                text = (base.rstrip("\n") + "\n\n" + text) if base.strip() else text
            saved.append(self.write(rel, text))
        return saved

    def drop_skeleton(self, m):
        """重做约定前先清掉本模块还是骨架的旧文件（实现过的不动，会被新约定的检查挡住 / 覆盖）。"""
        for rel, text in list((self.skel.get(m) or {}).items()):
            p = self.root / rel
            if not p.is_file():
                continue
            if SK.kind_of(rel) == "route":
                paths = {a["路径"] for a in (self.contracts.get(m) or {}).get("接口", []) if f"routes/{a['文件']}.zs" == rel}
                left = SK.cut_skeleton_blocks(p.read_text(encoding="utf-8"), paths)
                if left.strip():
                    p.write_text(left, encoding="utf-8", newline="")
                else:
                    p.unlink()
            elif SK.is_skeleton(p.read_text(encoding="utf-8")):
                p.unlink()
        self.skel.pop(m, None)
        self.frozen.pop(m, None)

    def skeleton_load_errs(self, m, contract, canon):
        """骨架落盘后跑一遍加载检查（接口头、执行调用、参数核对、整项目加载），有问题撤回返回错误列表；通过返回 ([], saved)。"""
        self.skel[m] = canon
        self.contracts[m] = contract
        saved = self.put_skeleton(m)
        errs = []
        own_flows = {f["名"]: {"入参": [p["名"] for p in f["入参"] if p["要求"] == "必填"], "可选入参": [p["名"] for p in f["入参"] if p["要求"] == "可选"]} for f in contract["流程"]}
        known = {**self.flowinfo, **own_flows}
        accessible = set(own_flows) | set(self.accessible_flows(m))
        for rel, text in canon.items():
            k = SK.kind_of(rel)
            if k == "route":
                errs += check_zs(text, rel, self.vpack, set(self.caps), True) + LC.check_text(text, rel, True)
            elif k == "flow":
                errs += check_zs(text, rel, self.vpack, set(self.caps), False) + LC.check_text(text, rel, False)
        calls = []
        for f in contract["流程"]:
            calls.append((f"scripts/{f['名']}.zs", f["调"]))
        for a in contract["接口"]:
            calls.append((f"routes/{a['文件']}.zs 接口 {a['路径']}", a["调用"]))
        for owner, cs in calls:
            text = "\n".join(f"设 r = 执行 scripts/{c['名']}.zs " + " ".join(f"{k}={{{k}}}" for k in c["给"]) for c in cs if c.get("类") == "流程")
            errs += check_calls(text, owner, known, accessible, self.disk_scripts())
        if not errs:
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                errs.append("骨架落盘后检查项目不过：" + str(b["msg"])[:500])
        if not errs:
            errs += [x for x in LC.check_project(self.root)]
        if errs:
            self.undo(saved)
            self.contracts.pop(m, None)
            self.skel.pop(m, None)
            return errs, []
        return [], saved

    def f_contract(self, rec, it, own=None):
        """一个模块的约定：模型写出骨架文件（≤2 次，程序解析 + 校验 + 加载检查，不过带报错重写）；通过就把规范骨架落到真实路径、冻结约定部分的快照。
        整份写超时（空闲 / 首字前静默 / 被杀，约定步骤的超时已单独放宽）或输出超长 → 改拆两次调用：先 sql + 流程，校验过再带着它们的骨架写 接口 + 界面。"""
        m = it["模块"]
        ctx = self.contract_ctx(m, own)      # own：重新约定时，上次冻结约定里本模块自己的 sql / 路径 / 动作（磁盘上已有实现，不算「被占用」）
        err = rec.get("上次失败") or "无"
        split = {}                           # 拆分模式的状态：{"head": 第一次已校验通过的 {路径: 文本}}；空 = 还没拆
        use_split = False
        for k in (1, 2):
            rec["规划尝试"] = k
            try:
                if use_split:
                    text = self.contract_split(rec, m, ctx, err, split)
                else:
                    try:
                        text = self.ask(self.contract_prompt(m, ctx, err), rec, "contract")
                    except FileFail as e:
                        if "模型没有完成输出" not in str(e):
                            raise
                        use_split = True
                        rec["拆分约定"] = str(e)[:120]
                        self.bump(2)
                        text = self.contract_split(rec, m, ctx, err, split)
            except _Retry as e:
                err = str(e)
                continue
            files, perr = SK.split_files(text)
            obj, perr2 = SK.extract(files) if files else ({}, [])
            if perr or perr2:
                err = "；".join(perr + perr2)
                continue
            r = C.validate_contract(obj, ctx)
            if not r["ok"]:
                err = "；".join(r["errors"])
                continue
            lerrs = self.accept_contract(rec, m, r["contract"])
            if not lerrs:
                return
            err = "；".join(lerrs)
        raise FileFail(f"约定两次没过：{err}"[:600])

    @staticmethod
    def _join_files(files):
        return "\n".join(f"=== {r} ===\n{t.rstrip()}" for r, t in files.items()) + "\n"

    def contract_split(self, rec, m, ctx, err, st):
        """拆分约定：第一次只写 sql + 流程（解析 + validate_contract 的 sql / 流程部分过了才算数，≤2 次，结果存进 st["head"]，之后重写第二次不再重做第一次）；
        第二次带着第一次已校验通过的骨架写 接口 + 界面。返回合起来的骨架文本，交给 f_contract 做整体校验。"""
        if "head" not in st:
            e1 = err
            for _k in (1, 2):
                try:
                    t1 = self.ask(self.contract_prompt(m, ctx, e1, part=1), rec, "contract")
                except _Retry as e:
                    e1 = str(e)
                    continue
                files, perr = SK.split_files(t1)
                late = [r for r in files if SK.kind_of(r) in ("route", "ui")]
                if late:
                    e1 = "这一次只写 queries/*.sql 与 scripts/*.zs，不要写 " + "、".join(late) + "（接口和界面下一次再写）"
                    continue
                obj, perr2 = SK.extract(files) if files else ({}, [])
                if perr or perr2:
                    e1 = "；".join(perr + perr2)
                    continue
                r = C.validate_contract(obj, {**ctx, "part": "sql_flow"})
                if not r["ok"]:
                    e1 = "；".join(r["errors"])
                    continue
                st["head"] = files
                rec["拆分第一次"] = "通过"
                break
            else:
                raise FileFail(f"约定拆成两次调用，第一次（sql + 流程）没过：{e1}"[:600])
        t2 = self.ask(self.contract_prompt(m, ctx, err, part=2, head=self._join_files(st["head"])), rec, "contract")
        files2, perr = SK.split_files(t2)
        if perr:
            raise _Retry("；".join(perr))
        keep = {r: t for r, t in files2.items() if SK.kind_of(r) in ("route", "ui")}      # 第二次误写的 sql / 流程丢掉，以第一次校验过的为准
        return self._join_files({**st["head"], **keep})

    def accept_contract(self, rec, m, contract):
        """校验过的约定 → 规范骨架落盘 + 加载检查 + 冻结快照。加载检查不过返回错误列表（调用方当一次失败尝试，带报错重写）。"""
        canon = SK.render(contract, {**self.action_map(), **{a["路径"]: a["动作"] for a in contract["接口"]}})
        lerrs, _saved = self.skeleton_load_errs(m, contract, canon)
        if lerrs:
            return ["骨架加载检查不过：" + x for x in lerrs]
        self.frozen[m] = SK.freeze(canon)
        rec.update(结果="通过", 产出={"sql": len(contract["sql"]), "流程": len(contract["流程"]), "接口": len(contract["接口"]), "界面": len(contract["界面"])})
        self.save_contracts()
        self.seed_from_contracts(m)
        self.claim(_dedup([h for g in ("sql", "流程", "接口") for x in contract[g] for h in x["规则"]]), self.cfile(m))
        return []

    def save_contracts(self):
        """contracts_frozen.json（约定部分快照，继续构建读它）；contracts.json / CONTRACTS.md 是从骨架生成的只读产物，给人看。"""
        (self.out / "contracts_frozen.json").write_text(json.dumps(self.frozen, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.out / "contracts.json").write_text(json.dumps(self.contracts, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.out / "CONTRACTS.md").write_text(C.contracts_md(self.top, self.contracts), encoding="utf-8")

    def seed_from_contracts(self, m):
        """约定一定下来，下游实现要对接的东西（sql 签名 / 流程签名 / 接口路径）就以约定为准，不等别的文件写成。"""
        c = self.contracts[m]
        self.msql[m] = {s["名"]: [p["名"] for p in s["参数"]] for s in c["sql"]}
        for s in c["sql"]:
            self.sql_owner[s["名"]] = f"queries/{m}_*.sql"
        for f in c["流程"]:
            r, o = C.req_opt(f["入参"])
            self.flowinfo[f["名"]] = {"模块": m, "入参": r, "可选入参": o, "出参": list(f["出参"]), "用sql": [x["名"] for x in f["调"] if x.get("类") == "sql"], "文件": f"scripts/{f['名']}.zs"}
        for a in c["接口"]:
            r, o = C.req_opt(a["请求字段"])
            self.paths[a["路径"]] = {"动作": a["动作"], "入参": [*r, *o], "文件": f"routes/{a['文件']}.zs", "实体": m, "说明": a["作用"]}
            self.acts.add(a["动作"])

    def reload_contract(self, m):
        """继续构建：上次冻结的快照 → 约定（按当前项目重新校验）。通过返回规范化的约定并把规范骨架补回磁盘（缺的才补）；不行返回 None。"""
        snap = self.loaded_frozen.get(m)
        if not snap:
            return None
        obj, errs = SK.thaw(snap)
        if errs:
            return None
        own = {"sql": {s["名"] for s in obj["sql"]}, "paths": {a["路径"] for a in obj["接口"]}, "acts": {a["动作"] for a in obj["接口"]}}
        r = C.validate_contract(obj, self.contract_ctx(m, own))
        if not r["ok"]:
            return None
        c = r["contract"]
        self.contracts[m] = c
        self.skel[m] = SK.render(c, {**self.action_map(), **{a["路径"]: a["动作"] for a in c["接口"]}})
        self.frozen[m] = snap
        for rel, text in self.skel[m].items():          # 磁盘上没有的骨架补回去（已实现的文件不动）
            if SK.kind_of(rel) == "route":
                have = {pp for _l, pp, _n, _b in P.blocks((self.root / rel).read_text(encoding="utf-8"))} if (self.root / rel).is_file() else set()
                miss = {a["路径"] for a in c["接口"] if f"routes/{a['文件']}.zs" == rel} - have
                if miss:
                    self.put_skeleton(m, {rel})
            elif not (self.root / rel).is_file():
                self.write(rel, text)
        return c

    def make_contracts(self):
        """数据层完成后：按构建顺序每个模块一次调用写出该模块的骨架文件（约定）；全部做完生成 CONTRACTS.md / contracts.json 并冻结。继续构建时读回冻结的快照，只补没做成的。"""
        for m in self.top["构建顺序"]:
            it = next(x for x in self.expected if x["文件"] == self.cfile(m))
            file = it["文件"]
            old = self.prev.get(file)
            if old and old["结果"] == "通过" and m in self.loaded_frozen and not self.bad_deps({"依赖": it["依赖"]}):
                c = self.reload_contract(m)
                if c is not None:
                    rec = dict(old)
                    rec["沿用"] = True
                    self.recs.append(rec)
                    self.state[file] = rec
                    self.seed_from_contracts(m)
                    self.claim(_dedup([h for g in ("sql", "流程", "接口") for x in c[g] for h in x["规则"]]), file)
                    continue
            rec = self.mrec("约定", file, m, it["依赖"])
            if old and old["结果"] in ("失败", "跳过") and old.get("失败原因"):
                rec["上次失败"] = f"上次运行失败：{old['失败原因']}"
            bad = self.bad_deps(rec)
            if bad:
                rec.update(结果="跳过", 失败原因="依赖没写成：" + "、".join(bad))
                continue
            if old and old["结果"] == "通过":
                self.bump(2)                 # 上次通过的约定这次不能沿用，要重新约定：补预算（bump_budget 没算它）
            own = None
            if m in self.loaded_frozen:
                self.skel.setdefault(m, {})
                self.drop_skeleton(m)
                try:
                    old_obj, _e = SK.thaw(self.loaded_frozen[m])
                    own = {"sql": {x["名"] for x in old_obj["sql"]}, "paths": {x["路径"] for x in old_obj["接口"]}, "acts": {x["动作"] for x in old_obj["接口"]}}
                except (KeyError, TypeError, AttributeError):
                    own = None
            try:
                self.f_contract(rec, it, own)
            except FileFail as e:
                rec.update(结果="失败", 失败原因=str(e)[:600])
            if rec["结果"] == "通过":
                self.changed.add(file)       # 约定重做过：依赖它的、上次通过的下游实现要重新按冻结快照比对，对不上就重做
        self.save_contracts()

    def skel_block(self, m, kind, rel=None):
        """给实现步骤看的骨架全文（约定部分一字不能改，占位换成实现）。"""
        fs = {r: t for r, t in (self.skel.get(m) or {}).items() if SK.kind_of(r) == kind and (rel is None or r == rel)}
        if not fs:
            return ""
        return "骨架文件（约定部分——sql 的 `-- 参数/返回/作用/表/用列/规则` 头注释、`#@` 行、接口头行——必须一字不改地保留，只把占位 `待实现` 换成真实实现；输出整份文件）：\n" + "\n".join(f"=== {r} ===\n{t.rstrip()}" for r, t in fs.items()) + "\n"

    def frozen_errs(self, m, rel, text):
        """实现的约定部分与冻结快照逐行一致。"""
        snap = (self.frozen.get(m) or {}).get(rel)
        return SK.check_frozen(rel, text, snap) if snap is not None else []

    # -- 约定模式：从约定派生单文件计划 / 对齐检查
    def contract_plan(self, layer, it):
        c = self.contracts[it["模块"]]
        if layer == "查询":
            return C.derive_sql(c)
        if layer == "流程":
            return C.derive_flow(next(f for f in c["流程"] if f["名"] == it["流程"]))
        if layer == "接口":
            return C.derive_iface([a for a in c["接口"] if a["文件"] == it["接口文件"]])
        return C.derive_ui(next(u for u in c["界面"] if u["页"] == it["页"]))

    @staticmethod
    def body_sqls(text):
        out = set()
        for raw in text.splitlines():
            mm = P.CALL.match(raw.strip())
            if mm:
                out.add(mm.group(3).removesuffix(".sql"))
        return out

    @staticmethod
    def body_flows(text):
        return {Path(path).stem for _ln, _bg, path, _kv, _line in zs_calls(text)}

    def contract_flow_errs(self, rel, body, fp):
        return C.check_calls_match(rel, body, fp["用sql"], fp["用流程"], self.body_sqls, self.body_flows)

    def contract_iface_errs(self, rel, body, items):
        """接口文件里新写的块要和约定逐项一致：路径集合、动作名、调用的流程 / sql、响应键。"""
        lines = body.splitlines()
        got = {path: (lines[ln0 - 1], "\n".join(l for _n, l in bl if not l.strip().startswith("#"))) for _m, path, ln0, bl in P.blocks(body)}      # 注释（含 #@ 声明行）不算实现
        want = {a["路径"]: a for a in items}
        errs = [f"{rel} 约定的接口 {p} 没写" for p in sorted(set(want) - set(got))]
        errs += [f"{rel} 多写了约定之外的接口 {p}（约定的：{sorted(want)}）" for p in sorted(set(got) - set(want))]
        for p, a in want.items():
            if p not in got:
                continue
            head, blk = got[p]
            mm = re.search(r"动作\s+(\S+)", head)
            if not mm or mm.group(1) != a["动作"]:
                errs.append(f"{rel} 接口 {p} 的动作名要是「{a['动作']}」（现在 {mm.group(1) if mm else '没写'}）")
            errs += C.check_calls_match(f"{rel} 接口 {p}", blk, a["用sql"], a["用流程"], self.body_sqls, self.body_flows)
            errs += C.check_response(p, a["响应"], blk)
        return errs

    @contextlib.contextmanager
    def qdir(self):
        """参数核对用的 queries 目录。约定模式下约定里有、磁盘上还没有（那个 sql 文件没写成）的 sql 用占位文件补上——流程 / 接口只对约定，不因 sql 文件没写成而过不了。"""
        d = self.root / "queries"
        miss = [(n, ps) for sq in self.msql.values() for n, ps in sq.items() if not (d / f"{n}.sql").is_file() or SK.is_skeleton((d / f"{n}.sql").read_text(encoding="utf-8"))] if self.contract_on else []
        if not miss:
            yield d
            return
        tmp = Path(tempfile.mkdtemp(prefix="mbq_"))
        try:
            if d.is_dir():
                for f in d.glob("*.sql"):
                    shutil.copyfile(f, tmp / f.name)
            for n, ps in miss:
                (tmp / f"{n}.sql").write_text("SELECT " + (", ".join(f":{x} AS {x}" for x in ps) or "1") + "\n", encoding="utf-8")
            yield tmp
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def sql_part(self, m, own):
        """给流程 / 接口生成看的本模块 sql：约定模式只给约定签名，不给实现全文。"""
        if self.contract_on:
            heads = "\n".join(f"=== queries/{s['名']}.sql ===\n" + "\n".join(l for l in SK.render_sql(s).splitlines() if l.startswith("-- ") and SK.MARK not in l)
                              for s in (self.contracts.get(m) or {}).get("sql", []))
            return f"本模块的 sql（骨架头部，不给实现）：\n{heads or '（无）'}\n"
        return f"本模块的 sql 全文：\n{self.sql_full(sorted(own))}\n"

    # -- 数据
    def layer_data(self, items):
        for it in items:
            self.run_file("数据", it["文件"], it["模块"], it["依赖"], self.f_entity, it)

    def f_entity(self, rec, it):
        m, rel = it["模块"], it["文件"]
        from tools.entity import parse
        expect = self.mod(m)["数据"]
        visible = self.visible_ents(m)
        dep_text = self.ent_text(self.dscope(m) - {m}) or "（无）"
        ctx = f"本模块：{self.mod_view(m)}\n依赖模块里已写好的实体全文：{dep_text}\n本文件：{rel}"
        fp = self.fplan(rec, self.pm["plan_ent"], ctx, lambda t: plan_entities(t, expect, visible))

        def attempt(err):
            text = self.ask(f"{self.pm['gen_ent']}\n需求：{self.task}\n{ctx}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"分配的规则：{self.rule_view(self.mod(m)['规则号'])}\n项目模板：{self.split['模板']}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or "要恰好一个实体文件块"
            body = blk["files"][0]["content"]
            try:
                names = [x.name for x in parse(body)]
            except Exception as ex:  # noqa: BLE001
                return f"实体解析失败：{ex}"
            if sorted(names) != sorted(expect) or len(set(names)) != len(names):
                return f"这个文件要恰好定义实体 {sorted(expect)}，现在定义了 {names or '（没有）'}"
            v = self.v["校验实体"]((self.ent_text() + "\n\n" + body).strip(), self.layers["模板"], self.task, self.layers["角色模板"])
            if v["ok"] != "是":
                return v["errors"]
            self.write(rel, body)
            return None
        self.gen_loop(rec, attempt)

    # -- 查询
    def layer_query(self, items):
        for it in items:
            self.run_file("查询", it["文件"], it["模块"], it["依赖"], self.f_query, it)

    def f_query(self, rec, it):
        m, rel = it["模块"], it["文件"]
        nums = self.mod(m)["规则号"]
        ents = self.ents_with_gen(self.dscope(m))
        taken = self.disk_sqls()
        gen_names = L.gen_sqls([e for mm in self.split["模块"].values() for e in mm["数据"]])
        dep_sigs = self.sig_text({s: p for d in self.dscope(m) - {m} for s, p in self.msql.get(d, {}).items()}, ())
        ctx = (f"本模块：{self.mod_view(m)}\n本模块与依赖模块的实体全文：{ents or '（无）'}\n项目里已有的 sql 名：{sorted(taken)}\n"
               f"依赖模块的定制 sql（只给名字参数）：{dep_sigs}\n分配的规则：{self.rule_view(nums)}")
        fp = self.contract_plan("查询", it) if self.contract_on else self.fplan(rec, self.pm["plan_sql"], ctx, lambda t: plan_sqls(t, m, set(nums), set(taken), gen_names))
        want = {s["名"]: set(s["参数"]) for s in fp["sql"]}
        for s in fp["sql"]:
            self.claim(s["规则"], rel)
        if not want:
            rec.update(结果="通过", 说明="无定制 sql", 产出=fp)
            self.msql[m] = {}
            return

        def attempt(err):
            skel = self.skel_block(m, "sql") if self.contract_on else ""
            text = self.ask(f"{self.pm['gen_sql']}\n需求：{self.task}\n本文件：{rel}\n本模块：{m}\n实体全文：{ents}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"{skel}分配的规则：{self.rule_view(nums)}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, f"queries/{m}_*.sql", "" if self.contract_on else "是")
            if blk["ok"] != "是":
                return blk.get("msg") or "没有 sql 块"
            got = {Path(f["file"]).stem: set(P.sql_params(f["content"])) for f in blk["files"]}
            errs = []
            for n in want:
                if n not in got:
                    errs.append(f"计划里的 sql「{n}」没写")
                elif got[n] != want[n]:
                    errs.append(f"sql「{n}」的参数与计划不符：计划 {sorted(want[n])}，实际 {sorted(got[n])}")
            errs += [f"多写了计划里没有的 sql「{n}」" for n in got if n not in want]
            if self.contract_on:         # 与约定一致：返回的列 / 写入（把语句在空库里真跑一遍看）
                items, esql = {s["名"]: s for s in self.contracts[m]["sql"]}, self.ents_sql()
                for f in blk["files"]:
                    n = Path(f["file"]).stem
                    if n in items:
                        errs += C.check_sql_returns(n, items[n], C.sql_result_cols(f["content"], esql))
                    errs += self.frozen_errs(m, f["file"], f["content"])
            opt = {x["名"]: x["可选参数"] for x in fp["sql"] if x.get("可选参数")}
            for f in blk["files"]:
                errs += check_optional_sql(Path(f["file"]).stem, f["content"], opt.get(Path(f["file"]).stem, []))
            if errs:
                return "；".join(errs)
            c = self.v["预编译sql"](blk, self.ent_text())
            if c["ok"] != "是":
                return c["msg"]
            for f in blk["files"]:
                self.write(f["file"], f["content"])
            return None
        self.gen_loop(rec, attempt)
        rec["产出"] = fp
        self.msql[m] = {s["名"]: list(s["参数"]) for s in fp["sql"]}
        for n in want:
            self.sql_owner[n] = rel

    # -- 流程
    def flow_order(self, items):
        """按构建顺序逐模块；同一模块内被调的流程在前（跨模块调用靠构建顺序：共用流程在归属模块，归属模块更早）。"""
        out = []
        for m in self.top["构建顺序"]:
            pend = [it for it in items if it["模块"] == m]
            names = {it["流程"] for it in pend}
            done = set()
            while pend:
                calls = lambda it: next(f["调流程"] for f in self.mod(m)["流程"] if f["名"] == it["流程"])      # noqa: E731
                nxt = next((it for it in pend if all(c in done or c not in names for c in calls(it))), pend[0])
                out.append(nxt)
                done.add(nxt["流程"])
                pend.remove(nxt)
        return out

    def layer_flow(self, items):
        for it in self.flow_order(items):
            self.run_file("流程", it["文件"], it["模块"], it["依赖"], self.f_flow, it)

    def f_flow(self, rec, it):
        m, rel, name = it["模块"], it["文件"], it["流程"]
        fdef = next(f for f in self.mod(m)["流程"] if f["名"] == name)
        nums = self.mod(m)["规则号"]
        sqls = self.visible_sqls(m)
        flows = self.accessible_flows(m)
        packs = set(self.mod(m)["能力"])
        verbs = {v for p in packs for v in [x["名"] for x in self.caps.get(p, [])]}
        own = {s: p for s, p in self.msql.get(m, {}).items()}
        cline = f"本流程的约定项（已冻结）：{json.dumps(next(f for f in self.contracts[m]['流程'] if f['名'] == name), ensure_ascii=False)}\n" if self.contract_on else ""
        ctx = (f"{cline}本流程：{json.dumps(fdef, ensure_ascii=False)}\n本模块：{self.mod_view(m)}\n本模块与依赖模块的实体全文：{self.ents_with_gen(self.dscope(m)) or '（无）'}\n"
               f"{self.sql_part(m, own)}依赖模块与 gen 自带 sql（名字参数）：{self.sig_text(sqls, own)}\n"
               f"已建好、可调的流程（签名）：{json.dumps({k: {x: v[x] for x in ('入参', '可选入参', '出参')} for k, v in flows.items()}, ensure_ascii=False)}\n"
               f"能力清单（本模块用到的包）：\n{self.cap_for(m)}\n分配的规则：{self.rule_view(nums)}")
        fp = self.contract_plan("流程", it) if self.contract_on else self.fplan(rec, self.pm["plan_flow"], ctx, lambda t: plan_flow(t, set(nums), set(sqls), set(flows), verbs, fdef["调流程"]))
        self.claim(fp["规则"], rel)
        decl_in = [*fp["入参"], *fp["可选入参"]]
        state = {"saved": [], "body": ""}
        used_sql = self.sql_full([s for s in fp["用sql"] if s in own])

        def attempt(err):
            skel = self.skel_block(m, "flow", rel) if self.contract_on else ""
            text = self.ask(f"{self.pm['gen_flow']}\n需求：{self.task}\n本文件：{rel}\n{ctx}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n{skel}"
                            f"用到的流程{'（骨架头部，不给实现）' if self.contract_on else '全文'}：\n{self.flow_text([f for f in fp['用流程']])}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "" if self.contract_on else "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or f"要恰好一个 {rel} 块"
            body = blk["files"][0]["content"]
            errs = check_zs(body, rel, self.vpack, set(self.caps), False) + LC.check_text(body, rel, False)
            if self.contract_on:
                errs += self.frozen_errs(m, rel, body)
            if not errs:
                wrapped, decl = wrap_flow(body, name, decl_in)
                with self.qdir() as qd:
                    pe, _ = P.check_text(wrapped, rel, qd, decl, P.identity_vars(self.root))
                errs += ["参数核对不过：" + x for x in pe]
                errs += check_calls(body, rel, self.flowinfo, set(flows), self.disk_scripts())
                if self.contract_on:
                    errs += self.contract_flow_errs(rel, body, fp)
                errs += check_sql_scope(body, rel, set(sqls))
                keys = set(RET_KEYS.findall("\n".join(l for l in body.splitlines() if l.strip().startswith("返回"))))
                miss = [k for k in fp["出参"] if k not in keys]
                if miss:
                    errs.append(f"{rel} 的「返回」里没有出参 {'、'.join(miss)}（计划的出参 {fp['出参']}）")
            if errs:
                return "；".join(errs)
            state["saved"] = [self.write(rel, body)]
            state["body"] = body
            return None
        unimpl = self.with_rules(rec, fp["规则"], attempt, state, lambda: (used_sql, state["body"]))
        rec["未实现规则"] = unimpl
        rec["产出"] = fp
        self.flowinfo[name] = {"模块": m, "入参": fp["入参"], "可选入参": fp["可选入参"], "出参": fp["出参"], "用sql": fp["用sql"], "文件": rel}

    def flow_text(self, names):
        if self.contract_on:
            fl = {f["名"]: f for c in self.contracts.values() for f in c["流程"]}
            return "\n".join(f"=== scripts/{n}.zs ===\n" + "\n".join(SK.flow_head(fl[n])) for n in names if n in fl) or "（无）"
        out = []
        for n in names:
            i = self.flowinfo.get(n)
            if i and (self.root / i["文件"]).is_file():
                out.append(f"-- {i['文件']}（入参 {i['入参']} 可选 {i['可选入参']} 出参 {i['出参']}）\n{(self.root / i['文件']).read_text(encoding='utf-8').strip()}")
        return "\n".join(out) or "（无）"

    def disk_scripts(self):
        d = self.root / "scripts"
        return {f"scripts/{f.name}" for f in d.glob("*.zs")} if d.is_dir() else set()

    def with_rules(self, rec, rules, attempt, state, ctx_fn):
        """生成（≤2 次）；有规则则核对一次，没实现的重写一轮（再核对一次），仍缺就记未实现。返回未实现规则文本列表。"""
        self.gen_loop(rec, attempt)
        if not rules:
            return []
        texts = self.rule_texts_m(rules)
        for rr in (1, 2):
            sqltxt, body = ctx_fn()
            try:
                chk = self.ask(f"{self.p['rule']}\n规则：{json.dumps(texts, ensure_ascii=False)} 本功能sql：{sqltxt} zs全文：{body}", rec, "plan")
            except (_Retry, FileFail):
                return []                         # 核对不了不拿它当理由重写
            except Halt:
                rec["未核对规则"] = texts         # 文件已过程序检查，只是规则没核对（熔断 / 预算用完）
                self.after_halt(rec)
                raise
            rec["核对"] = rec.get("核对", 0) + 1
            cr = self.v["核对规则"](chk, {"规则": texts})
            if cr["ok"] == "是":
                return []
            if rr == 2:
                return cr["未实现列表"]
            first = [(rel, (self.root / rel).read_text(encoding="utf-8")) for rel, _b in state["saved"]]
            self.undo(state["saved"])             # 先撤回第一版（接口文件是追加写，不撤会重复）
            try:
                why = attempt(f"以下业务规则没有实现，请补全（其余规则别丢）：{cr['未实现']}")
            except _Retry:
                why = "重写没有可用回复"
            except FileFail:
                why = "重写被中断"
            if why is not None:
                for rel, text in first:           # 重写没过检查：放回第一版（它过了检查），记未实现
                    self.write(rel, text)
                state["saved"] = [(rel, None) for rel, _t in first]
                return cr["未实现列表"]
        return []

    def after_halt(self, rec):
        rec["结果"] = "通过"

    def trial(self, items_by_file, rec=None):
        """试调检查：在项目副本里造数、按计划入参调新接口（见 trial.py）。返回问题列表（空 = 过）；试调本身跑不起来记「跳过」不算接口的错。"""
        if self.contract_on:
            items_by_file, why = self.trial_ready(items_by_file)
            if not items_by_file:
                if why and rec is not None:
                    rec["试调"] = {"调用": 0, "不过": 0, "跳过": why[0]}
                self.trials["跳过"] += why[:1]
                return []
        res = TR.run(self.root, items_by_file)
        flat = TR.problems_flat(res)
        self.trials["调用"] += res["calls"]
        self.trials["不过"] += len(flat)
        if res["skipped"]:
            self.trials["跳过"].append(res["skipped"])
        if rec is not None:
            rec["试调"] = {"调用": rec.get("试调", {}).get("调用", 0) + res["calls"], "不过": len(flat), **({"跳过": res["skipped"]} if res["skipped"] else {})}
        return flat

    def trial_ready(self, items_by_file):
        """约定模式：接口调到的流程 / sql（含流程再往下调的）文件都在磁盘上才试调；有没写成的，那个接口这次不试（别的文件失败了，不拿它当这个接口的错）。"""
        flows = {f["名"]: f for c in self.contracts.values() for f in c["流程"]}
        mine = {s for sq in self.msql.values() for s in sq}
        written = lambda p: p.is_file() and not SK.is_skeleton(p.read_text(encoding="utf-8"))      # noqa: E731  骨架占位还没换成实现 = 没写成

        def lacking(it):
            todo, seen, miss = [("流程", n) for n in it.get("用流程", [])] + [("sql", n) for n in it.get("用sql", [])], set(), []
            while todo:
                kind, n = todo.pop()
                if (kind, n) in seen:
                    continue
                seen.add((kind, n))
                if kind == "sql" and n in mine and not written(self.root / "queries" / f"{n}.sql"):
                    miss.append(f"queries/{n}.sql")
                elif kind == "流程":
                    if not written(self.root / "scripts" / f"{n}.zs"):
                        miss.append(f"scripts/{n}.zs")
                    todo += [(c.get("类") or "流程", c["名"]) for c in (flows.get(n) or {}).get("调", [])]
            return miss
        ready, why = {}, []
        for rel, its in items_by_file.items():
            for it in its:
                miss = lacking(it)
                if miss:
                    why.append(f"{rel} 接口 {it['路径']} 依赖的 {'、'.join(sorted(set(miss)))} 没写成，这次不试调")
                else:
                    ready.setdefault(rel, []).append(it)
        return ready, why

    def trial_round(self):
        """全部实现后统一试调一轮：不过的接口文件（及报错里点到名的流程 / sql 文件）带报错重写 1 轮，之后整体检查里再试调一遍。"""
        ok = {rel: items for rel, items in self.ifaces.items() if self.state.get(rel) and self.state[rel]["结果"] == "通过" and (self.root / rel).is_file()}
        ready, _why = self.trial_ready(ok)
        if not ready:
            return
        res = TR.run(self.root, ready)
        self.trials["调用"] += res["calls"]
        if res["skipped"]:
            self.trials["跳过"].append(res["skipped"])
        by_file = {it["文件"]: it for it in self.expected}
        redo = []
        for rel, errs in res["problems"].items():
            err = "；".join(errs)[:600]
            blame = []
            for it in ready[rel]:
                for f in it["用流程"]:
                    fi = self.flowinfo.get(f)
                    if fi and re.search(rf"(?<!\w){re.escape(f)}(?!\w)", err) and fi["文件"] in by_file:
                        blame.append(fi["文件"])
                for s in it["用sql"]:
                    own = self.sql_owner.get(s)
                    if own and own in by_file and re.search(rf"(?<!\w){re.escape(s)}(?!\w)", err):
                        blame.append(own)
            redo += [(f, err) for f in _dedup(blame)] + [(rel, err)]
        order = {"查询": 0, "流程": 1, "接口": 2}
        fns = {"查询": self.f_query, "流程": self.f_flow, "接口": self.f_iface}
        for file, err in sorted(_dedup(redo), key=lambda x: order[by_file[x[0]]["层"]]):
            it = by_file[file]
            old = self.state.get(file)
            if not old or it["层"] not in fns:
                continue
            self.discard_stale(it["层"], file, old)
            self.recs.remove(old)
            self.state.pop(file, None)
            self.prev[file] = {"结果": "失败", "失败原因": f"试调不过：{err}"}
            self.bump(8)
            rec = self.run_file(it["层"], file, it["模块"], it["依赖"], fns[it["层"]], it)
            rec["试调重写"] = True

    # -- 接口
    def layer_iface(self, items):
        for it in items:
            self.run_file("接口", it["文件"], it["模块"], it["依赖"], self.f_iface, it)

    def f_iface(self, rec, it):
        m, rel, ifile = it["模块"], it["文件"], it["接口文件"]
        nums = self.mod(m)["规则号"]
        sqls = self.visible_sqls(m)
        flows = self.accessible_flows(m)
        must = [f["名"] for mm in self.split["模块"].values() for f in mm["流程"] if ifile in f["用于"]]
        routes = self.v["项目摘要"]({"含参数": "是"})["routes"]
        taken_paths = ({x["path"] for x in routes} if self.contract_on else set(self.paths) | {x["path"] for x in routes})
        taken_acts = ({x["action"] for x in routes if x.get("action")} if self.contract_on else set(self.acts) | {x["action"] for x in routes if x.get("action")})
        own = self.msql.get(m, {})
        ents = self.ents_with_gen(self.dscope(m))
        cline = (f"本文件的约定项（已冻结）：{json.dumps([a for a in self.contracts[m]['接口'] if a['文件'] == ifile], ensure_ascii=False)}\n") if self.contract_on else ""
        ctx = (f"{cline}本文件：{rel}\n本模块：{self.mod_view(m)}\n本模块与依赖模块的实体全文：{ents or '（无）'}\n{self.sql_part(m, own)}"
               f"依赖模块与 gen 自带 sql（名字参数）：{self.sig_text(sqls, own)}\n"
               f"已建好、可调的流程（签名）：{json.dumps({k: {x: v[x] for x in ('入参', '可选入参', '出参')} for k, v in flows.items()}, ensure_ascii=False)}\n"
               f"本文件必须用的流程：{must}\n项目角色：{json.dumps(self.layers['角色'], ensure_ascii=False)}\n已被占用的接口路径：{sorted(taken_paths)}\n"
               f"能力清单（本模块用到的包）：\n{self.cap_for(m)}\n分配的规则：{self.rule_view(nums)}")
        fp = self.contract_plan("接口", it) if self.contract_on else self.fplan(rec, self.pm["plan_iface"], ctx, lambda t: plan_ifaces(t, self.layers["角色"], set(nums), taken_paths, taken_acts, set(sqls), flows, must))
        rules = _dedup([h for a in fp["接口"] for h in a["规则"]])
        self.claim(rules, rel)
        decl = {a["路径"]: a["入参"] for a in fp["接口"]}
        used_f = _dedup([f for a in fp["接口"] for f in a["用流程"]])
        used_s = _dedup([s for a in fp["接口"] for s in a["用sql"]])
        state = {"saved": [], "body": ""}
        path = self.root / rel

        def attempt(err):
            summary = self.v["项目摘要"]({"含参数": "是"})["text"]
            skel = self.skel_block(m, "route", rel) if self.contract_on else ""
            text = self.ask(f"{self.pm['gen_iface']}\n需求：{self.task}\n{ctx}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n{skel}"
                            f"用到的流程{'（骨架头部，不给实现）' if self.contract_on else '全文'}：\n{self.flow_text(used_f)}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "" if self.contract_on else "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or f"要恰好一个 {rel} 块（sql 在查询层已经建好，这里不要写）"
            body = blk["files"][0]["content"]
            errs = check_zs(body, rel, self.vpack, set(self.caps), True) + LC.check_text(body, rel, True)
            if self.contract_on:
                errs += self.frozen_errs(m, rel, body)
            if errs:
                return "；".join(errs)
            base = path.read_text(encoding="utf-8") if path.is_file() else ""
            if self.contract_on:         # 骨架块（占位）换成实现；同一文件里 gen 的 CRUD 块原样留着
                base = SK.cut_skeleton_blocks(base, {a["路径"] for a in fp["接口"]})
            merged = (base.rstrip("\n") + "\n\n" + body) if base.strip() else body      # routes/<实体>.zs 是 gen 的 CRUD 文件：追加不覆盖
            saved = [self.write(rel, merged)]
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                self.undo(saved)
                return b["msg"]
            rc = self.v["校验角色"]({"名": m, "接口": fp["接口"]})
            if rc["ok"] != "是":
                self.undo(saved)
                return rc["msg"]
            with self.qdir() as qd:
                pe, _ = P.check_text(body, rel, qd, decl, P.identity_vars(self.root))
            errs = ["参数核对不过：" + x for x in pe]
            errs += check_calls(body, rel, self.flowinfo, set(flows), self.disk_scripts())
            errs += check_sql_scope(body, rel, set(sqls))
            if self.contract_on:
                errs += self.contract_iface_errs(rel, body, fp["接口"])
            if not errs:
                errs += self.trial({rel: fp["接口"]}, rec)
            if errs:
                self.undo(saved)
                return "；".join(errs)
            state["saved"], state["body"] = saved, body
            return None
        unimpl = self.with_rules(rec, rules, attempt, state, lambda: (self.sql_full(used_s), state["body"] + "\n" + self.flow_text(used_f)))
        rec["未实现规则"] = unimpl
        rec["产出"] = fp
        self.ifaces[rel] = fp["接口"]
        for a in fp["接口"]:
            self.paths[a["路径"]] = {"动作": a["动作"], "入参": a["入参"], "文件": rel, "实体": m, "说明": a["说明"]}
            self.acts.add(a["动作"])

    # -- 界面
    def layer_ui(self, items):
        for it in items:
            self.run_file("界面", it["文件"], it["模块"], it["依赖"], self.f_ui, it)

    def f_ui(self, rec, it):
        m, rel, page = it["模块"], it["文件"], it["页"]
        avail = set(self.paths) | {x["path"] for x in self.v["项目摘要"]({"含参数": "是"})["routes"]}
        ents = self.ent_text(self.dscope(m))
        pdef = next(p for p in self.mod(m)["界面"] if p["名"] == page)
        listing = [{"路径": p, **{k: v[k] for k in ("动作", "入参", "说明")}} for p, v in self.paths.items() if v["实体"] == m]
        ctx = (f"本页：{json.dumps(pdef, ensure_ascii=False)}\n本模块：{self.mod_view(m)}\n涉及的实体全文：{ents or '（无）'}\n本模块已建的接口：{json.dumps(listing, ensure_ascii=False)}\n"
               f"全部可用接口路径（含 gen 自带的增删改查）：{sorted(avail)}")
        fp = self.contract_plan("界面", it) if self.contract_on else self.fplan(rec, self.pm["plan_ui"], ctx, lambda t: S.plan_ui(t, avail))
        used = sorted({u for pg in fp["页面"] for u in pg["用接口"]})
        info = []
        for p in used:
            v = self.paths.get(p)
            info.append({"路径": p, "动作": v["动作"], "入参": v["入参"], "文件": v["文件"], "说明": v["说明"]} if v
                        else {"路径": p, "说明": "gen 自动生成的增删改查接口（动作名见全项目名字摘要）"})

        def attempt(err):
            summary = self.v["项目摘要"]({"含参数": "是"})["text"]
            skel = self.skel_block(m, "ui", rel) if self.contract_on else ""
            text = self.ask(f"{self.pm['gen_ui']}\n需求：{self.task}\n涉及的实体全文：{ents}\n本文件：{rel}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n{skel}"
                            f"用接口对应的接口/动作/入参：{json.dumps(info, ensure_ascii=False)}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "" if self.contract_on else "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or "要恰好一个文件块"
            if self.contract_on:
                ferr = self.frozen_errs(m, rel, blk["files"][0]["content"])
                if ferr:
                    return "；".join(ferr)
            saved = [self.write(rel, blk["files"][0]["content"])]
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                self.undo(saved)
                return b["msg"]
            if self.contract_on:         # 与约定一致：界面用的远程动作正好是「用接口」对应的动作
                known = {i["路径"]: i["动作"] for c in self.contracts.values() for i in c["接口"]}
                known.update({x["path"]: x["action"] for x in self.v["项目摘要"]({"含参数": "是"})["routes"] if x.get("action")})
                errs = C.check_ui_actions(page, blk["files"][0]["content"], {known[u] for u in used if u in known})
                if errs:
                    self.undo(saved)
                    return "；".join(errs)
            return None
        self.gen_loop(rec, attempt)

    # ------------------------------------------------------------ 4 整体检查
    def final(self):
        problems = []
        self.reapply_perms()      # 模型追加接口后再确认一遍 gen 块的权限
        if self.fatal:
            problems.append(self.fatal)
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            problems.append("整体检查不过：" + b["msg"])
        ident = P.identity_vars(self.root)
        by_rel = {r["文件"]: r for r in self.recs}
        for rel, items in self.ifaces.items():
            r, f = by_rel.get(rel), self.root / rel
            if r and r["结果"] == "通过" and f.is_file():
                text = f.read_text(encoding="utf-8")
                pe, _ = P.check_text(text, rel, self.root / "queries", {a["路径"]: a["入参"] for a in items}, ident)
                problems += [x for x in pe if any(f"接口 {a['路径']}" in x for a in items)]     # gen 的 CRUD 在同一文件里：只认本计划声明过路径的接口块
                problems += [x for x in check_calls(text, rel, self.flowinfo, set(self.flowinfo), self.disk_scripts())]
                problems += [x for x in check_zs(self.iface_body(text, items), rel, self.vpack, set(self.caps), True)]
                problems += LC.check_text(self.iface_body(text, items), rel, True)
        for name, i in self.flowinfo.items():
            f = self.root / i["文件"]
            r = by_rel.get(i["文件"])
            if r and r["结果"] == "通过" and f.is_file():
                text = f.read_text(encoding="utf-8")
                problems += check_zs(text, i["文件"], self.vpack, set(self.caps), False)
                problems += LC.check_text(text, i["文件"], False)
                wrapped, decl = wrap_flow(text, name, [*i["入参"], *i["可选入参"]])
                problems += P.check_text(wrapped, i["文件"], self.root / "queries", decl, ident)[0]
                problems += check_calls(text, i["文件"], self.flowinfo, set(self.flowinfo), self.disk_scripts())
        # 全项目按服务启动的方式加载一遍（含 gen 的 CRUD 与模型追加的接口）：零「接口出错」
        problems += LC.check_project(self.root)
        # 全项目试调：所有通过的新接口文件各调一遍，汇总
        ok_ifaces = {rel: items for rel, items in self.ifaces.items() if by_rel.get(rel) and by_rel[rel]["结果"] == "通过" and (self.root / rel).is_file()}
        if ok_ifaces:
            problems += self.trial(ok_ifaces)
        for h, t in self.split["规则表"].items():
            if h not in self.claimed:
                self.unclaimed.append(f"{h}：{t}")
        return problems

    unclaimed = ()

    @staticmethod
    def iface_body(text, items):
        """只取本计划声明过路径的接口块（文件里还有 gen 的 CRUD 块）。"""
        out = []
        for method, path, ln0, lines in P.blocks(text):
            if any(a["路径"] == path for a in items):
                out.append(text.splitlines()[ln0 - 1])
                out += [l for _n, l in lines]
                out.append("结束")
        return "\n".join(out)

    # ------------------------------------------------------------ 主流程
    def drive(self):
        self.unclaimed = []
        (self.out / "capabilities.md").write_text(cap_markdown(self.caps), encoding="utf-8")
        if self.resume:
            self.start_resume()
        elif self.from_plan:
            self.start_plan()
        else:
            self.make_top()
            if self.fatal:
                return
            self.make_split()
            if self.fatal:
                return
        self.build_all()

    def start_plan(self):
        """从已有规划开始：顶层规划和层次×模块读旧运行的，在新目录写 plan/top.zs / plan/layers.zs（旧目录是 JSON 规划的转成 DSL）和 PLAN.md / LAYERS.md，从数据层做起。"""
        self.top, self.split = self.from_plan["top"], self.from_plan["split"]
        self.deps = top_deps(self.top)
        self.layers = {"模板": self.split["模板"], "角色": self.split["角色"], "角色模板": self.split["角色模板"], "层": self.split["层"], "规则表": self.split["规则表"]}
        self.save_plan("top.zs", PD.render_top(self.top))
        self.save_plan("layers.zs", PD.render_layers(self.split))
        (self.out / "PLAN.md").write_text(plan_md(self.top), encoding="utf-8")
        (self.out / "LAYERS.md").write_text(layers_md(self.top, self.split), encoding="utf-8")
        self.plan_files()

    def start_resume(self):
        """继续构建：顶层规划和层次×模块从上次保存的结果读回，不调模型。"""
        R = self.resume
        self.top, self.split = R["top"], R["split"]
        self.deps = top_deps(self.top)
        self.layers = {"模板": self.split["模板"], "角色": self.split["角色"], "角色模板": self.split["角色模板"],
                       "层": self.split["层"], "规则表": self.split["规则表"]}
        (self.out / "PLAN.md").write_text(plan_md(self.top), encoding="utf-8")
        (self.out / "LAYERS.md").write_text(layers_md(self.top, self.split), encoding="utf-8")
        self.plan_files()


def run_modular(M, task, project, stop_cls, cap=None, max_calls=None, out_dir=None, verbs_root=None, resume=None, codex_cap=None, contract=False, from_plan=None):
    """跑完整个流程，返回 {状态, 结论, 原因, 文件, 清单, 整体问题, 花费, codex调用, 顶层规划, 层次, 本次}。不抛业务错误（Stop 在这里接住）。
    resume：restore_state() 的结果，给了就是继续构建（不重做两步规划，沿用上次通过且仍过检查的文件，其余按原顺序重做；cap 只算本次新花的）。"""
    r = ModRun(M, task, project, stop_cls, cap, out_dir, verbs_root, resume, codex_cap, contract, from_plan)
    r.user_max = max_calls
    halt = None
    try:
        r.drive()
    except Halt as h:
        halt = h
    problems = []
    if not r.fatal and r.split and r.recs:
        try:
            problems = r.final()
        except Exception as e:  # noqa: BLE001
            problems = [f"整体检查出错：{type(e).__name__}: {e}"]
    if r.split and halt:       # 被熔断 / 预算停下时，层次×模块里还没建记录的文件记「未做」（继续构建时没轮到的文件保留上次的记录）
        have = {x["文件"] for x in r.recs}
        for f in r.expected:
            if f["文件"] not in have:
                if f["文件"] in r.prev:
                    rec = dict(r.prev[f["文件"]])
                    rec["本次未轮到"] = True
                    r.recs.append(rec)
                    r.state[f["文件"]] = rec
                else:
                    r.mrec(f["层"], f["文件"], f["模块"], f["依赖"])
    lay = None
    if r.split:
        lay = {"模板": r.split["模板"], "角色": r.split["角色"], "层": r.split["层"], "规则数": len(r.split["规则表"]), "文件数": len(r.expected),
               "模块": {n: {"依赖": v["依赖"], "数据": v["数据"], "流程": [f["名"] for f in v["流程"]], "接口": [f["文件"] for f in v["接口"]],
                           "界面": [f["名"] for f in v["界面"]], "能力": v["能力"], "缺口": v["缺口"]} for n, v in r.split["模块"].items()},
               "构建顺序": r.top["构建顺序"], "批次": [], "调用上限": M.max_calls}
    out = LY.conclude(r, M, halt, problems, cap, lay)
    if r.split and r.unclaimed and out["结论"] == "成功":
        out.update(状态="失败", 结论="部分成功", 原因="部分成功：规则没有落到任何文件：" + "；".join(r.unclaimed))
    elif r.unclaimed:
        out["原因"] += "；规则没有落到任何文件：" + "；".join(r.unclaimed)
    mine = [x for x in r.recs if x.get("运行") == r.run_no and not x.get("沿用") and not x.get("本次未轮到")]
    out["本次"] = {"序号": r.run_no, "沿用": sum(1 for x in r.recs if x.get("沿用")), "重做": len(mine),
                 "文件": [{k: x.get(k) for k in ("文件", "层", "模块", "结果", "失败原因", "调用", "规划尝试", "生成尝试", "静默重试", "上次失败", "因上游变化重做", "排回待做", "回退", "试调", "试调重写") if x.get(k) not in (None, "", 0)} | {"文件": x["文件"], "结果": x["结果"]}
                        for x in mine]}
    out.update(顶层规划=r.top, 层次=None if not r.split else {k: r.split[k] for k in ("模板", "角色", "层", "层说明", "全局约束", "规则表")},
               规则未覆盖=list(r.unclaimed), 试调=r.trials, 约定模式=r.contract_on,
               约定={m: {k: len(c[k]) for k in ("sql", "流程", "接口", "界面")} for m, c in r.contracts.items()})
    return out


def main(argv=None):
    """python -m tools.dslagent.modbuild restore <out_dir> [需求文件]：把上次输出目录里的顶层规划 / 层次×模块还原成 plan/top.zs / plan/layers.zs（继续构建会自动做这步，这里单独验证用）。"""
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 2 or a[0] != "restore":
        print(main.__doc__)
        return 2
    task = Path(a[2]).read_text(encoding="utf-8") if len(a) > 2 else ""
    try:
        st = restore_state(a[1], task)
    except ResumeError as e:
        print("还原失败：" + str(e))
        return 1
    print(json.dumps({"模块": st["top"]["构建顺序"], "文件记录": len(st["files"]), "运行次数": st["run_no"] - 1, "已用调用": st["n0"], "累计花费": st["prior_cost"],
                      "从哪还原": st["restored"] or ["plan/top.zs / plan/layers.zs"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
