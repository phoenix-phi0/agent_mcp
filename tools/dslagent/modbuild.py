"""newproj --modular：顶层规划 → 层次 × 模块 → 按层逐层构建（旧 newproj / split / layered 不动）。

对照真实项目 kg/ 的七层：能力层 verbs/（现成 Python 动词）、数据层 entities/<模块>.entity、查询层 queries/<模块>_*.sql、
流程层 scripts/<名>.zs（多个接口共用的业务流程）、接口层 routes/<模块>.zs、界面层 ui/<页>.ui。调用方向 界面→接口→流程→查询→数据，能力层任何层可用，不许往上调。

流程（v2.run_newproj(modular=True) 调 run_modular()）：
  0 能力清单（程序）：用 VerbRegistry 加载 verbs/ 下每个包，抽出动词名 / 参数 / 一句话说明 → capabilities.md（输出目录）。
  1 顶层规划（模型 1 次，不过重写，共 ≤2 次）：目标 / 使用者 / 主流程 / 模块（依赖）/ 共用流程归属 / 横切 / 构建顺序；validate_top 校验 → PLAN.md。
  2 层次 × 模块（模型 1 次，≤2 次）：层、模块（规则 / 数据 / 流程 / 接口 / 界面 / 能力 / 缺口）；validate_split 校验（与顶层模块一致等）→ LAYERS.md。
  3 逐层构建，层内按顶层「构建顺序」逐模块：数据（建库＋gen 增删改查＋检查项目）→ 查询 → 流程 → 接口 → 界面。每个文件先单独规划（≤2 次）再生成（≤2 次）。
    失败的文件撤回、记失败，依赖它的上层文件跳过；超长 / 被杀＝该文件失败不终止；花费熔断（--cost-cap）沿用。
  4 整体检查：检查项目 + 全部 zs 的动词 / 参数 / 调用核对 → 成功 / 部分成功 / 失败。
模型调用、单文件失败隔离、熔断、检查动词（校验实体 / 预编译sql / 检查项目 / 校验角色 / 核对规则 / 参数核对）都复用 layered.py。
"""
import json
import re
import sys
import tempfile
from pathlib import Path

from . import layered as LY
from . import guard as G      # noqa: F401
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
        errs.append(f"模板「{tpl}」不对，只能是 default / full / private")
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
        rs = _strs(s.get("规则"), f"sql「{n}」的规则", errs)
        for h in rs:
            if h not in rule_nums:
                errs.append(f"sql「{n}」的规则「{h}」不是分给本模块的规则 {sorted(rule_nums)}")
        out.append({"名": n, "参数": ps, "说明": str(s.get("说明") or ""), "规则": rs})
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
        out.append({"路径": p, "动作": an, "角色": ar, "入参": ins, "用sql": us, "用流程": uf, "调用": {k: list(v) for k, v in calls.items() if isinstance(v, list)},
                    "规则": rs, "说明": str(a.get("说明") or "")})
    for f in must_flows:
        if f not in usedf:
            errs.append(f"层次×模块规定流程「{f}」给本文件用，但没有接口的「用流程」里写它")
    return {"接口": out}, errs


# ================================================================== 3 逐层构建

class ModRun(LY.Run):
    def __init__(self, M, task, project, stop_cls, cap=None, out_dir=None, verbs_root=None):
        super().__init__(M, task, project, stop_cls, cap)
        self.out = Path(out_dir) if out_dir else self.root
        self.caps = capabilities(verbs_root)
        self.vpack = verb_packs(self.caps)
        self.pm = {n: _prompt(f"sys_m{n}.md") for n in ("top", "split", "plan_ent", "plan_sql", "plan_flow", "plan_iface", "plan_ui",
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
        g = self.v["生成增删改查"]({"项目目录": ".", "模板": self.layers["模板"], "角色": self.layers["角色"]})
        if g["ok"] != "是":
            self.fatal = f"生成增删改查不过：{g['msg']}"
            return
        b = self.v["检查项目"]({})
        if b["ok"] != "是":
            self.fatal = f"gen 生成的项目检查不过：{b['msg']}"

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
        return rec

    def run_file(self, layer, file, m, deps, fn, *a):
        rec = self.mrec(layer, file, m, deps)
        bad = self.bad_deps(rec)
        if bad:
            rec.update(结果="跳过", 失败原因="依赖的文件没写成：" + "、".join(bad))
            return rec
        try:
            fn(rec, *a)
        except FileFail as e:
            rec.update(结果="失败", 失败原因=str(e)[:600])
        return rec

    def fplan(self, rec, sysp, body, validate):
        """单文件规划 ≤2 次：校验不过带报错重写；两次不过抛 FileFail。"""
        err = "无"
        for k in (1, 2):
            rec["规划尝试"] = k
            try:
                text = self.ask(f"{sysp}\n需求：{self.task}\n{body}\n上次的报错：{err}", rec)
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
            n += 4 if f["层"] in ("数据", "查询", "界面") else 8
        self.bump(n)

    # ------------------------------------------------------------ 1 顶层规划
    def make_top(self):
        st = self.step("顶层规划")
        self.bump(2)
        err = "无"
        for k in (1, 2):
            st["尝试"] = k
            try:
                text = self.ask(f"{self.pm['top']}\n需求：{self.task}\n现有动词包（能力清单，只列动词名）：\n{cap_text(self.caps, brief=True)}\n上次的报错：{err}", st)
            except _Retry as e:
                err = str(e)
                continue
            except FileFail as e:
                self.fatal = f"顶层规划没有完成：{e}"
                return
            r = validate_top(text, set(self.caps), self.task)
            if r["ok"]:
                self.top = r["top"]
                self.deps = top_deps(self.top)
                (self.out / "PLAN.md").write_text(plan_md(self.top), encoding="utf-8")
                return
            err = "；".join(r["errors"])
        self.fatal = f"顶层规划两次都没过：{err}"[:800]

    # ------------------------------------------------------------ 2 层次 × 模块
    def make_split(self):
        st = self.step("层次×模块")
        self.bump(2)
        err = "无"
        for k in (1, 2):
            st["尝试"] = k
            try:
                text = self.ask(f"{self.pm['split']}\n需求：{self.task}\n顶层规划：{self.top_view()}\n能力清单（动词名按包分）：\n{cap_text(self.caps, brief=True)}\n上次的报错：{err}", st)
            except _Retry as e:
                err = str(e)
                continue
            except FileFail as e:
                self.fatal = f"层次×模块没有完成：{e}"
                return
            r = validate_split(text, self.top, self.caps, self.task)
            if r["ok"]:
                self.split = r["split"]
                self.layers = {"模板": self.split["模板"], "角色": self.split["角色"], "角色模板": self.split["角色模板"],
                               "层": self.split["层"], "规则表": self.split["规则表"]}
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
        self.expected = ex
        self.bump_budget()

    # ------------------------------------------------------------ 3 逐层构建
    def build_all(self):
        fns = {"数据": self.layer_data, "查询": self.layer_query, "流程": self.layer_flow, "接口": self.layer_iface, "界面": self.layer_ui}
        for layer in BUILD_LAYERS:
            if self.fatal:
                return
            fns[layer]([f for f in self.expected if f["层"] == layer])
            if layer == "数据":
                self.gen()

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
        ents = self.ent_text(self.dscope(m))
        taken = self.disk_sqls()
        gen_names = L.gen_sqls([e for mm in self.split["模块"].values() for e in mm["数据"]])
        dep_sigs = self.sig_text({s: p for d in self.dscope(m) - {m} for s, p in self.msql.get(d, {}).items()}, ())
        ctx = (f"本模块：{self.mod_view(m)}\n本模块与依赖模块的实体全文：{ents or '（无）'}\n项目里已有的 sql 名：{sorted(taken)}\n"
               f"依赖模块的定制 sql（只给名字参数）：{dep_sigs}\n分配的规则：{self.rule_view(nums)}")
        fp = self.fplan(rec, self.pm["plan_sql"], ctx, lambda t: plan_sqls(t, m, set(nums), set(taken), gen_names))
        want = {s["名"]: set(s["参数"]) for s in fp["sql"]}
        for s in fp["sql"]:
            self.claim(s["规则"], rel)
        if not want:
            rec.update(结果="通过", 说明="无定制 sql")
            self.msql[m] = {}
            return

        def attempt(err):
            text = self.ask(f"{self.pm['gen_sql']}\n需求：{self.task}\n本文件：{rel}\n本模块：{m}\n实体全文：{ents}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"分配的规则：{self.rule_view(nums)}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, f"queries/{m}_*.sql", "是")
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
            if errs:
                return "；".join(errs)
            c = self.v["预编译sql"](blk, self.ent_text())
            if c["ok"] != "是":
                return c["msg"]
            for f in blk["files"]:
                self.write(f["file"], f["content"])
            return None
        self.gen_loop(rec, attempt)
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
        ctx = (f"本流程：{json.dumps(fdef, ensure_ascii=False)}\n本模块：{self.mod_view(m)}\n本模块与依赖模块的实体全文：{self.ent_text(self.dscope(m)) or '（无）'}\n"
               f"本模块的 sql 全文：\n{self.sql_full(sorted(own))}\n依赖模块与 gen 自带 sql（名字参数）：{self.sig_text(sqls, own)}\n"
               f"已建好、可调的流程（签名）：{json.dumps({k: {x: v[x] for x in ('入参', '可选入参', '出参')} for k, v in flows.items()}, ensure_ascii=False)}\n"
               f"能力清单（本模块用到的包）：\n{self.cap_for(m)}\n分配的规则：{self.rule_view(nums)}")
        fp = self.fplan(rec, self.pm["plan_flow"], ctx, lambda t: plan_flow(t, set(nums), set(sqls), set(flows), verbs, fdef["调流程"]))
        self.claim(fp["规则"], rel)
        decl_in = [*fp["入参"], *fp["可选入参"]]
        state = {"saved": [], "body": ""}
        used_sql = self.sql_full([s for s in fp["用sql"] if s in own])

        def attempt(err):
            text = self.ask(f"{self.pm['gen_flow']}\n需求：{self.task}\n本文件：{rel}\n{ctx}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"用到的流程全文：\n{self.flow_text([f for f in fp['用流程']])}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or f"要恰好一个 {rel} 块"
            body = blk["files"][0]["content"]
            errs = check_zs(body, rel, self.vpack, set(self.caps), False)
            if not errs:
                wrapped, decl = wrap_flow(body, name, decl_in)
                pe, _ = P.check_text(wrapped, rel, self.root / "queries", decl, P.identity_vars(self.root))
                errs += ["参数核对不过：" + x for x in pe]
                errs += check_calls(body, rel, self.flowinfo, set(flows), self.disk_scripts())
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
        self.flowinfo[name] = {"模块": m, "入参": fp["入参"], "可选入参": fp["可选入参"], "出参": fp["出参"], "用sql": fp["用sql"], "文件": rel}

    def flow_text(self, names):
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
                chk = self.ask(f"{self.p['rule']}\n规则：{json.dumps(texts, ensure_ascii=False)} 本功能sql：{sqltxt} zs全文：{body}", rec)
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
        taken_paths = set(self.paths) | {x["path"] for x in routes}
        taken_acts = set(self.acts) | {x["action"] for x in routes if x.get("action")}
        own = self.msql.get(m, {})
        ents = self.ent_text(self.dscope(m))
        ctx = (f"本文件：{rel}\n本模块：{self.mod_view(m)}\n本模块与依赖模块的实体全文：{ents or '（无）'}\n本模块的 sql 全文：\n{self.sql_full(sorted(own))}\n"
               f"依赖模块与 gen 自带 sql（名字参数）：{self.sig_text(sqls, own)}\n"
               f"已建好、可调的流程（签名）：{json.dumps({k: {x: v[x] for x in ('入参', '可选入参', '出参')} for k, v in flows.items()}, ensure_ascii=False)}\n"
               f"本文件必须用的流程：{must}\n项目角色：{json.dumps(self.layers['角色'], ensure_ascii=False)}\n已被占用的接口路径：{sorted(taken_paths)}\n"
               f"能力清单（本模块用到的包）：\n{self.cap_for(m)}\n分配的规则：{self.rule_view(nums)}")
        fp = self.fplan(rec, self.pm["plan_iface"], ctx, lambda t: plan_ifaces(t, self.layers["角色"], set(nums), taken_paths, taken_acts, set(sqls), flows, must))
        rules = _dedup([h for a in fp["接口"] for h in a["规则"]])
        self.claim(rules, rel)
        decl = {a["路径"]: a["入参"] for a in fp["接口"]}
        used_f = _dedup([f for a in fp["接口"] for f in a["用流程"]])
        used_s = _dedup([s for a in fp["接口"] for s in a["用sql"]])
        state = {"saved": [], "body": ""}
        path = self.root / rel

        def attempt(err):
            summary = self.v["项目摘要"]({"含参数": "是"})["text"]
            text = self.ask(f"{self.pm['gen_iface']}\n需求：{self.task}\n{ctx}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"用到的流程全文：\n{self.flow_text(used_f)}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or f"要恰好一个 {rel} 块（sql 在查询层已经建好，这里不要写）"
            body = blk["files"][0]["content"]
            errs = check_zs(body, rel, self.vpack, set(self.caps), True)
            if errs:
                return "；".join(errs)
            merged = (path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + body) if path.is_file() else body      # routes/<实体>.zs 是 gen 的 CRUD 文件：追加不覆盖
            saved = [self.write(rel, merged)]
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                self.undo(saved)
                return b["msg"]
            rc = self.v["校验角色"]({"名": m, "接口": fp["接口"]})
            if rc["ok"] != "是":
                self.undo(saved)
                return rc["msg"]
            pe, _ = P.check_text(body, rel, self.root / "queries", decl, P.identity_vars(self.root))
            errs = ["参数核对不过：" + x for x in pe]
            errs += check_calls(body, rel, self.flowinfo, set(flows), self.disk_scripts())
            errs += check_sql_scope(body, rel, set(sqls))
            if errs:
                self.undo(saved)
                return "；".join(errs)
            state["saved"], state["body"] = saved, body
            return None
        unimpl = self.with_rules(rec, rules, attempt, state, lambda: (self.sql_full(used_s), state["body"] + "\n" + self.flow_text(used_f)))
        rec["未实现规则"] = unimpl
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
        fp = self.fplan(rec, self.pm["plan_ui"], ctx, lambda t: S.plan_ui(t, avail))
        used = sorted({u for pg in fp["页面"] for u in pg["用接口"]})
        info = []
        for p in used:
            v = self.paths.get(p)
            info.append({"路径": p, "动作": v["动作"], "入参": v["入参"], "文件": v["文件"], "说明": v["说明"]} if v
                        else {"路径": p, "说明": "gen 自动生成的增删改查接口（动作名见全项目名字摘要）"})

        def attempt(err):
            summary = self.v["项目摘要"]({"含参数": "是"})["text"]
            text = self.ask(f"{self.pm['gen_ui']}\n需求：{self.task}\n涉及的实体全文：{ents}\n本文件：{rel}\n单文件计划：{json.dumps(fp, ensure_ascii=False)}\n"
                            f"用接口对应的接口/动作/入参：{json.dumps(info, ensure_ascii=False)}\n全项目名字摘要：{summary}\n上次的报错：{err}", rec)
            blk = self.v["拆分隔块"](text, rel, "是")
            if blk["ok"] != "是" or blk["n"] != 1:
                return blk.get("msg") or "要恰好一个文件块"
            saved = [self.write(rel, blk["files"][0]["content"])]
            b = self.v["检查项目"]({})
            if b["ok"] != "是":
                self.undo(saved)
                return b["msg"]
            return None
        self.gen_loop(rec, attempt)

    # ------------------------------------------------------------ 4 整体检查
    def final(self):
        problems = []
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
        for name, i in self.flowinfo.items():
            f = self.root / i["文件"]
            r = by_rel.get(i["文件"])
            if r and r["结果"] == "通过" and f.is_file():
                text = f.read_text(encoding="utf-8")
                problems += check_zs(text, i["文件"], self.vpack, set(self.caps), False)
                wrapped, decl = wrap_flow(text, name, [*i["入参"], *i["可选入参"]])
                problems += P.check_text(wrapped, i["文件"], self.root / "queries", decl, ident)[0]
                problems += check_calls(text, i["文件"], self.flowinfo, set(self.flowinfo), self.disk_scripts())
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
        self.make_top()
        if self.fatal:
            return
        self.make_split()
        if self.fatal:
            return
        self.build_all()


def run_modular(M, task, project, stop_cls, cap=None, max_calls=None, out_dir=None, verbs_root=None):
    """跑完整个流程，返回 {状态, 结论, 原因, 文件, 清单, 整体问题, 花费, codex调用, 顶层规划, 层次}。不抛业务错误（Stop 在这里接住）。"""
    r = ModRun(M, task, project, stop_cls, cap, out_dir, verbs_root)
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
    if r.split and halt:       # 被熔断 / 预算停下时，层次×模块里还没建记录的文件记「未做」
        have = {x["文件"] for x in r.recs}
        for f in r.expected:
            if f["文件"] not in have:
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
    out.update(顶层规划=r.top, 层次=None if not r.split else {k: r.split[k] for k in ("模板", "角色", "层", "层说明", "全局约束", "规则表")},
               规则未覆盖=list(r.unclaimed))
    return out
