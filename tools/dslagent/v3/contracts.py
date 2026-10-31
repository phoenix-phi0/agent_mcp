"""约定规划 contracts/<模块>.md 的检查：dslproj 的约定检查（格式、跨模块调用必须是依赖且上游有该公开函数、接口指向公开函数、
每个公开函数有用例、多余依赖……）+ v3 另加：约定的「依赖」必须是 plan/top.zs 里的模块且不成环（不要求与 top.zs 逐字一致，
全部约定过后用「同步顶层依赖」动词同步）、表名以「模块名」或「模块名_」开头（各模块的表不重名）。
确定性，不调模型。

豁免（K174）：两条规则在约定里显式标注后不报——在被报的那一行（「表 …」行 / 用例的「调用 …」行）正上方写一行注释：
    # 约定检查豁免 表名前缀：<理由>
    # 约定检查豁免 可选传空 <入参> [<入参>…]：<理由>
  可选传空 只该在「传空和不传本来就是同一件事、用例期望与不传时一致」时用（如单人模式 current_role 传空、「名称为空不改名」）；
  「传空=清空、不传=不改」这种真矛盾不该豁免（K148 assist_material.改材料_标题为空）。注释行解析时本来就跳过，不影响代码与用例。
  理由不能空；豁免没对上下一行的违约（规则 / 入参对不上、下一行已经不违约）也作为问题报出，免得豁免过期了还留着。
  豁免是给人审过之后写的：问题文字里不提示这个写法（免得规划模型为了过检查自己加豁免）。
"""
import re
from pathlib import Path

from ..packs.dslproj import contract as C
from . import top as T


def path_of(project, module):
    return Path(project) / "contracts" / f"{module}.md"


def upstream_of(project, name, deps):
    """→ ({上游: 约定}, 问题)：deps 里每个模块读 contracts/<m>.md 并解析；读不到 / 解析不过记问题。"""
    ups, probs = {}, []
    for d in deps:
        f = path_of(project, d)
        if not f.is_file():
            probs.append(f"依赖的模块「{d}」还没有约定文件（contracts/{d}.md）")
            continue
        uc, p = C.parse(f.read_text(encoding="utf-8"))
        if p:
            probs.append(f"上游 contracts/{d}.md 解析不通过：{p[0]}")
        else:
            ups[d] = uc
    return ups, probs


def cycle_with(project, name, deps, mods):
    """用已通过的约定（没通过的模块退回 top 里缺省的依赖）搭一张依赖图，把 name 的依赖换成 deps → 有环返回环上的名字列表，没有返回 None。"""
    graph = {}
    for m, d in mods.items():
        if m == name:
            graph[m] = list(deps)
            continue
        try:
            uc, _ = load(project, m)
            graph[m] = uc["依赖"]
        except FileNotFoundError:
            graph[m] = d
    return T.find_cycle(graph)


def ui_action_problems(project, name, c, mods):
    """项目有 ui/*.ui 时对接口「动作」声明的核对（K25；.ui 是前端的输入，解析用 tools.ui_actions）：
    - 本约定声明的动作必须在某个 .ui 里真的有人调（声明动作只为绑前端；项目没有 .ui 时不该有「动作」）；
    - 每个 .ui 远程动作都要有接口声明它：等其余模块的约定都落盘后才做全量核对——写约定按依赖分层并行，
      先写的模块核对时别人的还没有，缺不算错；最后一份过检查时全量核对（gen build 的 missing_endpoint 是最终兜底）。"""
    try:
        from tools import ui_actions as UA
        uis = UA.remote_names(project)
    except Exception:  # noqa: BLE001  .ui 语法错由 gen build / 界面编译报
        return []
    probs = []
    mine = {i["动作"] for i in c["接口"] if i["动作"]}
    if not uis:
        if mine:
            probs.append("项目没有 ui/*.ui（或里面没有远程动作），接口不用声明「动作 …」——那是给前端绑定用的；删掉："
                         + "、".join(sorted(mine)))
        return probs
    for a in sorted(mine - uis):
        probs.append(f"接口声明了「动作 {a}」，但项目 ui/*.ui 里没有这个远程动作（声明「动作」是给前端绑定用的；"
                     f"动作名要和 .ui 里「动作 <名> 远程」一字不差）")
    if any(m != name and not path_of(project, m).is_file() for m in mods):
        return probs          # 还有模块没写完约定，覆盖核对放到最后一份过检查时
    decl = {}
    for m in mods:
        if m == name:
            cc = c
        else:
            uc, p = C.parse(path_of(project, m).read_text(encoding="utf-8"))
            if p:
                continue
            cc = uc
        for i in cc["接口"]:
            if i["动作"]:
                decl.setdefault(i["动作"], []).append(m)
    for a in sorted(uis):
        hit = decl.get(a, [])
        if not hit:
            probs.append(f"前端 .ui 的远程动作「{a}」还没有任何接口声明「动作 {a}」：要在拥有它的模块的约定「## 接口」里"
                         f"写一行 POST 接口并带上「动作 {a}」（前端只会 POST）")
        elif len(hit) > 1:
            probs.append(f"前端动作「{a}」被模块 {'、'.join(hit)} 都声明了，一个动作名只能绑一个接口")
    return probs


def check(text, name, top, project):
    """→ 问题列表（空 = 通过）。top：top.load 的结果；project：读上游约定的项目目录。"""
    mods = {m["名"]: m["依赖"] for m in top["模块"]}
    if name not in mods:
        return [f"模块「{name}」不在 plan/top.zs 里"]
    c, probs = C.parse(text)
    ups, up_probs = upstream_of(project, name, c["依赖"] or mods[name])
    probs += up_probs
    probs += C.check(c, name, ups, list(mods))
    # 依赖与 top.zs 不要求逐字一致：只要依赖的是 top.zs 里的模块（上面已查）且不成环就放行；
    # 全部约定过后由「同步顶层依赖」把 top.zs 改成与约定一致。
    cyc = cycle_with(project, name, c["依赖"], mods)
    if cyc:
        probs.append("约定的「依赖」会和已有约定一起成环：" + " → ".join(cyc))
    probs += exempted(text, table_prefix(c, name) + optional_empty_hits(c))
    probs += provides_missing(c, name, top)
    probs += ui_action_problems(project, name, c, list(mods))
    seen = set()
    return [p for p in probs if not (p in seen or seen.add(p))]


def provides_missing(c, name, top):
    """top.zs 里本模块「提供」的函数，约定里必须都有且是「公开 函数」。→ 问题列表。"""
    mine = next((m for m in top["模块"] if m["名"] == name), None)
    fns = {f["名"]: f for f in c["函数"]}
    probs = []
    for fn in (mine or {}).get("提供", []):
        if fn not in fns:
            probs.append(f"top.zs 里模块「{name}」提供「{fn}」（别的模块要调用），但约定里没有这个函数：请加「公开 函数 {fn} …」")
        elif not fns[fn]["公开"]:
            probs.append(f"top.zs 里模块「{name}」提供「{fn}」（别的模块要调用），约定里它不是公开函数：请改成「公开 函数 {fn} …」")
    return probs


def table_prefix(c, name):
    """表名没以「模块名」或「模块名_」开头 → [(行, 规则, 入参, 问题)]。"""
    return [(t["行"], "表名前缀", "", f"第 {t['行']} 行：表名「{t['名']}」要以「{name}_」开头（各模块的表不重名）")
            for t in c["表"] if t["名"] != name and not t["名"].startswith(name + "_")]


def optional_empty_hits(c):
    """用例里给「可选入参」传「空」：可选入参不传和传空串都是空串，函数里分不出来，这样的用例没法由实现满足
    （常见错法：'传空表示清空、不传表示不改'）。→ [(行, 规则, 入参, 问题)]。"""
    fns = {f["名"]: f for f in c["函数"]}
    hits = []
    for u in c["用例"]:
        call = u["调用"]
        f = fns.get(call["目标"]) if call else None
        if f is None:
            continue
        opt = set(C.params(f)[1])
        for k, v in call["参数"].items():
            if k in opt and v in ("空", ""):
                hits.append((call["行"], "可选传空", k,
                             f"第 {call['行']} 行：用例 {u['名']} 给可选入参 {k} 传了「空」，可选入参不传和传空串都是空串，函数分不出来，"
                             f"这样的用例实现没法满足（想表达清空 / 置空，请把它改成必填入参或另做一个函数）"))
    return hits


def optional_empty(c):
    """→ 问题列表（不看豁免）。"""
    return [h[3] for h in optional_empty_hits(c)]


EXEMPT_RE = re.compile(r"^\s*#\s*约定检查豁免\s*([^\s：:]*)((?:\s+[A-Za-z_][A-Za-z0-9_]*)*)\s*(?:[：:]\s*(.*))?$")
EXEMPT_RULES = ("表名前缀", "可选传空")


def exemptions(text):
    """约定里的豁免注释 → ({目标行: [{行, 规则, 入参, 理由}]}, 问题)。目标行 = 注释下面第一个不是注释、不是空行的行。"""
    lines = text.replace("\r", "").splitlines()
    out, probs = {}, []
    for i, raw in enumerate(lines):
        m = EXEMPT_RE.match(raw)
        if not m:
            continue
        no, rule, params, why = i + 1, m.group(1), m.group(2).split(), (m.group(3) or "").strip()
        if rule not in EXEMPT_RULES:
            probs.append(f"第 {no} 行：约定检查豁免只认 {' / '.join(EXEMPT_RULES)}，现在是「{rule}」")
            continue
        if not why:
            probs.append(f"第 {no} 行：约定检查豁免要写理由（「# 约定检查豁免 {rule}{''.join(' ' + p for p in params)}：理由」）")
            continue
        if rule == "可选传空" and not params:
            probs.append(f"第 {no} 行：可选传空 的豁免要写明豁免哪个入参（「# 约定检查豁免 可选传空 <入参>：理由」）")
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
            j += 1
        out.setdefault(j + 1, []).append({"行": no, "规则": rule, "入参": params if rule == "可选传空" else [""], "理由": why})
    return out, probs


def exempted(text, hits):
    """hits：[(行, 规则, 入参, 问题)] → 去掉被豁免的之后的问题列表，加上豁免本身的问题（写法不对、没对上违约）。"""
    ex, probs = exemptions(text)
    used, out = set(), []
    for no, rule, param, msg in hits:
        k = next((k for k, e in enumerate(ex.get(no, [])) if e["规则"] == rule and param in e["入参"]), None)
        if k is None:
            out.append(msg)
        else:
            used.add((no, k, param))
    for no, es in sorted(ex.items()):
        for k, e in enumerate(es):
            idle = [p for p in e["入参"] if (no, k, p) not in used]
            if idle:
                what = e["规则"] + "".join(" " + p for p in idle if p)
                probs.append(f"第 {e['行']} 行：约定检查豁免（{what}）没有对上第 {no} 行的违约，删掉或改对")
    return out + probs


def check_project(project, top):
    """plan/top.zs 里每个有 contracts/<模块>.md 的模块逐个 check → [{issue, modules, basis}]（audit2 开头的约定闸用，不调模型）。
    还没有约定文件的模块不查（那是规划没做完，不是约定写错）。"""
    items = []
    for m in top["模块"]:
        f = path_of(project, m["名"])
        if not f.is_file():
            continue
        for p in check(f.read_text(encoding="utf-8"), m["名"], top, project):
            items.append({"issue": p, "modules": m["名"], "basis": f"约定检查 contracts/{m['名']}.md"})
    return items


def load(project, name):
    """通过检查后的约定 → (contract, 原文)；读不到抛 FileNotFoundError。"""
    text = path_of(project, name).read_text(encoding="utf-8")
    return C.parse(text)[0], text


def digest(c):
    """给记录用的摘要：函数 / 公开函数 / 接口 / 用例 / 表数。"""
    return {"表": len(c["表"]), "函数": len(c["函数"]), "公开函数": sum(1 for f in c["函数"] if f["公开"]),
            "接口": len(c["接口"]), "用例": len(c["用例"])}
