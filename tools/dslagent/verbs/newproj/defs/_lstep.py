"""三级规划（layered.py）三步的 JSON 解析与校验。下划线开头，scan_verbs 不注册；layered.py 直接 import。
（_layer.py 是旧的一次性全量分层清单，layered.py 不再用它的 validate，只借它的 parse / 常量。）

一、确认分层（validate_layers）：
  {"模板":"default|full|private","角色":["teacher","student"],"规则":[{"号":"R1","文":"需求原句"}],"层":["实体","查询","接口","界面"]}
二、确认文件（validate_files，可分批）：
  {"文件":[{"层":"接口","路径":"routes/attempt.zs","实体":"attempt","作用":"一句话","规则":["R1"],"依赖":["entities/attempt.entity","queries/attempt_*.sql"]}]}
三、单文件规划（plan_entity / plan_query / plan_iface / plan_ui），每层一种：
  实体 {"字段":[{"名","类型","说明"}],"关联":["question"],"约束":["…"]}
  查询 {"sql":[{"名","参数":[],"说明","规则":["R3"]}]}
  接口 {"接口":[{"路径","动作","角色","入参":[],"用sql":[],"规则":[],"说明"}],"新sql":[{"名","参数":[],"说明"}]}
  界面 {"页面":[{"名","说明","用接口":["/path"],"字段":["f"]}]}
"""
import re

from _layer import FENCE, GEN_PATH_SUFFIX, GEN_SQL_SUFFIX, ROLE_HINT, SNAKE, TEMPLATES, gen_paths, gen_sqls, parse   # noqa: F401

LAYERS = ("实体", "查询", "接口", "界面")
IDENT = re.compile(r"^[A-Za-z_]\w*$")


def _strs(v, what, errs):
    if v in (None, ""):
        return []
    if not isinstance(v, list) or not all(isinstance(i, str) and i.strip() for i in v):
        errs.append(f"{what} 要是非空文本列表")
        return []
    return [i.strip() for i in v]


# ------------------------------------------------------------------ 一、分层

def validate_layers(x, task=""):
    obj, err = parse(x)
    if err:
        return {"ok": False, "errors": [err]}
    errs = []
    tpl = str(obj.get("模板") or "").strip()
    if tpl not in TEMPLATES:
        errs.append(f"模板「{tpl}」不对，只能是 default / full / private")
    roles = _strs(obj.get("角色"), "「角色」", errs)
    for r in roles:
        if not SNAKE.match(r):
            errs.append(f"角色「{r}」要是英文小写 snake（如 teacher）")
    if len(set(roles)) != len(roles):
        errs.append("「角色」里有重复项")
    if roles and tpl != "private":
        errs.append("给了「角色」，模板必须是 private（登录注册靠 private 生成）")
    if not roles and str(task or "").strip() and ROLE_HINT.search(str(task)):
        errs.append("需求里提到了登录 / 账号 / 角色 / 权限，必须给「角色」（如 [\"teacher\",\"student\"]，注册默认角色放最后）并选 private 模板")
    rules, raw = {}, obj.get("规则")
    if raw not in (None, "") and not isinstance(raw, list):
        errs.append("「规则」要是列表")
        raw = []
    for i, r in enumerate(raw or [], 1):
        if not isinstance(r, dict) or not str(r.get("号") or "").strip() or not str(r.get("文") or "").strip():
            errs.append(f"规则第 {i} 项要是 {{\"号\":\"R1\",\"文\":\"原句\"}}，两个都不能空")
            continue
        h = str(r["号"]).strip()
        if h in rules:
            errs.append(f"规则号「{h}」重复")
        rules[h] = str(r["文"]).strip()
    ls = obj.get("层")
    if not isinstance(ls, list) or not ls or not all(isinstance(i, str) for i in ls):
        errs.append("「层」要是文本列表，如 [\"实体\",\"查询\",\"接口\",\"界面\"]")
        ls = []
    for n in ls:
        if n not in LAYERS:
            errs.append(f"层「{n}」不对，只能从 {'/'.join(LAYERS)} 里选（增删改查由程序生成，不算层）")
    if len(set(ls)) != len(ls):
        errs.append("「层」里有重复项")
    if ls and "实体" not in ls:
        errs.append("「层」必须包含「实体」")
    if rules and ls and "查询" not in ls and "接口" not in ls:
        errs.append("有业务规则，「层」里至少要有「查询」或「接口」，规则才有地方落地")
    out = {"ok": not errs, "errors": errs}
    if not errs:
        out.update(模板=tpl, 角色=roles, 角色模板="private" if roles else "", 规则表=rules, 层=[n for n in LAYERS if n in ls])
    return out


# ------------------------------------------------------------------ 二、文件

def _path_ok(layer, path, ent):
    """路径是否合规：返回 (合规, 期望写法)。"""
    if layer == "实体":
        return path == f"entities/{ent}.entity", f"entities/{ent}.entity"
    if layer == "查询":
        return path == f"queries/{ent}_*.sql", f"queries/{ent}_*.sql（含星号，一个实体一项，里面有几条 sql 后面单文件规划再定）"
    if layer == "接口":
        return bool(re.fullmatch(rf"routes/{re.escape(ent)}(?:_[a-z0-9_]+)?\.zs", path)), f"routes/{ent}.zs 或 routes/{ent}_<后缀>.zs"
    return bool(re.fullmatch(r"ui/[a-z][a-z0-9_]*\.ui", path)), "ui/<英文小写名>.ui"


def validate_files(x, layers, rules, known=(), allow=None, final=True, tpl=""):
    """x：模型输出；layers：第一步确认的层；rules：规则表 {号: 文}；known：之前批次已接受的文件项；allow：本批允许的层（缺省全部确认的层）；
    final：最后一批（才查规则覆盖）。返回 {ok, errors（按类汇总的文本列表）, files（本批规范化后的文件项）}。"""
    obj, err = parse(x)
    if err:
        return {"ok": False, "errors": [f"格式：{err.replace('清单', '文件清单')}"], "files": []}
    allow = list(allow or layers)
    cats = {}

    def bad(cat, msg):
        cats.setdefault(cat, []).append(msg)

    raw = obj.get("文件")
    if not isinstance(raw, list) or not raw:
        return {"ok": False, "errors": ["格式：要有「文件」列表，每项 {层, 路径, 实体, 作用, 规则, 依赖}"], "files": []}
    known = [dict(k) for k in known]
    by_path = {k["路径"]: k for k in known}
    order = {n: i for i, n in enumerate(LAYERS)}
    new = []
    for i, f in enumerate(raw, 1):
        if not isinstance(f, dict):
            bad("格式", f"第 {i} 项要是对象")
            continue
        layer, path, ent = f.get("层"), f.get("路径"), str(f.get("实体") or "").strip()
        if layer not in layers:
            bad("层", f"第 {i} 项的层「{layer}」不在已确认的层 {layers} 里")
            continue
        if layer not in allow:
            bad("层", f"本批只列 {'、'.join(allow)} 层的文件，不要列「{layer}」层（第 {i} 项 {path}）")
            continue
        if not isinstance(path, str) or not path.strip():
            bad("格式", f"第 {i} 项缺「路径」")
            continue
        path = path.strip()
        if layer != "界面" or ent:
            if not SNAKE.match(ent):
                bad("命名", f"{path} 的「实体」「{ent}」要是英文小写 snake")
                continue
        ok, want = _path_ok(layer, path, ent)
        if not ok:
            bad("命名", f"{layer}层文件「{path}」命名不合规，实体「{ent}」应写 {want}")
            continue
        if path in by_path:
            bad("路径", f"路径「{path}」重复")
            continue
        if layer == "实体" and ent == "user" and tpl == "private":
            bad("命名", "private 模板的 user 实体由 gen 生成，不要列 user")
            continue
        es = []
        item = {"层": layer, "路径": path, "实体": ent, "作用": str(f.get("作用") or "").strip(),
                "规则": _strs(f.get("规则"), f"{path} 的「规则」", es), "依赖": _strs(f.get("依赖"), f"{path} 的「依赖」", es)}
        for e in es:
            bad("格式", e)
        by_path[path] = item
        new.append(item)
    allf = known + new
    ent_files = {k["实体"] for k in allf if k["层"] == "实体"}
    for k in new:
        if k["实体"] and k["层"] != "实体" and k["实体"] not in ent_files:
            bad("实体", f"{k['路径']} 用到实体「{k['实体']}」，但没有 entities/{k['实体']}.entity 这个实体文件（先把它列在实体层）")
    # 依赖方向：只指向更低层，或同层且已排在前面
    pos = {k["路径"]: n for n, k in enumerate(allf)}
    for k in new:
        mine = order[k["层"]]
        deps = list(k["依赖"])
        own = f"entities/{k['实体']}.entity"
        if k["层"] in ("查询", "接口") and own in by_path and own not in deps:
            deps.insert(0, own)         # 补全：查询 / 接口文件必然依赖自己主实体的实体文件
        for d in deps:
            t = by_path.get(d)
            if d == k["路径"]:
                bad("依赖", f"{d} 不能依赖自己")
            elif t is None:
                bad("依赖", f"{k['路径']} 依赖的「{d}」不在文件清单里（只能依赖清单里列了的文件，路径照抄）")
            elif order[t["层"]] > mine:
                bad("依赖", f"{k['路径']}（{k['层']}层）不能依赖更高层的 {d}（{t['层']}层）")
            elif order[t["层"]] == mine and pos[d] > pos[k["路径"]]:
                bad("依赖", f"{k['路径']} 依赖同层的 {d}，但它排在后面，把 {d} 挪到前面")
        k["依赖"] = deps
    # 规则
    assigned = set()
    for k in allf:
        for h in k["规则"]:
            if h not in rules:
                bad("规则", f"{k['路径']} 的规则号「{h}」没在第一步确认的规则里")
            if k["层"] in ("查询", "接口"):
                assigned.add(h)
    if final:
        for h, t in rules.items():
            if h not in assigned:
                bad("规则", f"规则 {h}「{t[:30]}」没有分到任何查询层或接口层文件（在对应文件的「规则」里写上 {h}）")
    if "实体" in allow and not [k for k in allf if k["层"] == "实体"]:
        bad("实体", "实体层一个文件都没有：至少列一个 entities/<实体>.entity")
    errors = [f"{c}：{'；'.join(m)}" for c, m in cats.items()]
    return {"ok": not errors, "errors": errors, "files": new}


# ------------------------------------------------------------------ 三、单文件规划

def _obj(x):
    o, err = parse(x)
    return (o, "") if not err else (None, err.replace("清单", "规划"))


def plan_entity(x, dep_ents):
    """dep_ents：本文件依赖的（已写好的）实体名。"""
    o, err = _obj(x)
    if err:
        return None, [err]
    errs = []
    fs = o.get("字段")
    if not isinstance(fs, list) or not fs:
        errs.append("「字段」要是非空列表：[{\"名\":\"title\",\"类型\":\"文本\",\"说明\":\"题干\"}]")
        fs = []
    out = []
    for i, f in enumerate(fs, 1):
        n = f.get("名") if isinstance(f, dict) else None
        if not isinstance(n, str) or not SNAKE.match(n) or n == "id":
            errs.append(f"字段第 {i} 项的名「{n}」要是英文小写 snake，且不能叫 id")
            continue
        out.append({"名": n, "类型": str((f.get("类型") or "")), "说明": str(f.get("说明") or "")})
    rel = _strs(o.get("关联"), "「关联」", errs)
    for r in rel:
        if r not in dep_ents:
            errs.append(f"关联「{r}」不是本文件依赖的、已写好的实体（可选：{sorted(dep_ents) or '没有'}）；要关联它就得先在文件清单的「依赖」里列上")
    return {"字段": out, "关联": rel, "约束": _strs(o.get("约束"), "「约束」", errs)}, errs


def plan_query(x, ent, assigned, taken):
    """taken：项目里已有的 sql 名（磁盘上的）。"""
    o, err = _obj(x)
    if err:
        return None, [err]
    errs = []
    ss = o.get("sql")
    if not isinstance(ss, list) or not ss:
        errs.append("「sql」要是非空列表：[{\"名\":\"" + ent + "_pick\",\"参数\":[\"learner\"],\"说明\":\"…\",\"规则\":[\"R3\"]}]")
        ss = []
    gen = gen_sqls({ent})
    seen, out, covered = set(), [], set()
    for s in ss:
        n = s.get("名") if isinstance(s, dict) else None
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"sql 名「{n}」要是英文小写 snake")
            continue
        if not n.startswith(ent + "_"):
            errs.append(f"sql 名「{n}」要以「{ent}_」开头")
        if n in gen:
            errs.append(f"sql 名「{n}」与 gen 自动生成的重名（{'/'.join(GEN_SQL_SUFFIX)} 五条不用写）")
        elif n in taken:
            errs.append(f"sql 名「{n}」项目里已经有了，换个名字")
        if n in seen:
            errs.append(f"sql 名「{n}」重复")
        seen.add(n)
        rs = _strs(s.get("规则"), f"sql「{n}」的规则", errs)
        for h in rs:
            if h not in assigned:
                errs.append(f"sql「{n}」的规则「{h}」不是分给本文件的规则 {sorted(assigned)}")
        covered |= set(rs)
        out.append({"名": n, "参数": _strs(s.get("参数"), f"sql「{n}」的参数", errs), "说明": str(s.get("说明") or ""), "规则": rs})
    for h in sorted(set(assigned) - covered):
        errs.append(f"分给本文件的规则 {h} 没有落到任何一条 sql 的「规则」里")
    return {"sql": out}, errs


def plan_iface(x, ent, assigned, roles, taken_paths, taken_acts, avail_sqls):
    """avail_sqls：磁盘上已有的 sql 名；taken_paths / taken_acts：项目里已有的接口路径 / 动作名（含 gen 的 CRUD）。"""
    o, err = _obj(x)
    if err:
        return None, [err]
    errs = []
    new_raw = o.get("新sql")
    if new_raw in (None, ""):
        new_raw = []
    if not isinstance(new_raw, list):
        errs.append("「新sql」要是列表（不需要新 sql 就写 []）")
        new_raw = []
    gen = gen_sqls({ent})
    news, nset = [], set()
    for s in new_raw:
        n = s.get("名") if isinstance(s, dict) else None
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"新sql 名「{n}」要是英文小写 snake")
            continue
        if not n.startswith(ent + "_"):
            errs.append(f"新sql「{n}」只能放 queries/{ent}_*.sql，名字要以「{ent}_」开头（本文件主实体是 {ent}）")
        if n in gen or n in avail_sqls:
            errs.append(f"新sql「{n}」已经存在（项目里或 gen 自带），直接写进「用sql」，别当新的")
        if n in nset:
            errs.append(f"新sql「{n}」重复")
        nset.add(n)
        news.append({"名": n, "参数": _strs(s.get("参数"), f"新sql「{n}」的参数", errs), "说明": str(s.get("说明") or "")})
    its = o.get("接口")
    if not isinstance(its, list) or not its:
        errs.append("「接口」要是非空列表，每项 {路径, 动作, 角色, 入参, 用sql, 规则, 说明}")
        its = []
    paths, acts, out, covered = set(), set(), [], set()
    for a in its:
        if not isinstance(a, dict):
            errs.append("接口项要是对象")
            continue
        p, an = a.get("路径"), a.get("动作")
        if not isinstance(p, str) or not p.startswith("/"):
            errs.append(f"接口路径「{p}」要以 / 开头")
        elif p in taken_paths or p in paths:
            errs.append(f"接口路径「{p}」已被占用" + ("（gen 自动生成的 CRUD 路径或别的文件的接口）" if p in taken_paths else "（本文件内重复）"))
        paths.add(p)
        if not isinstance(an, str) or not SNAKE.match(an):
            errs.append(f"接口「{p}」的动作名「{an}」要是英文小写 snake")
        elif an in taken_acts or an in acts:
            errs.append(f"动作名「{an}」已被占用，换一个")
        acts.add(an)
        ar = a.get("角色") or ""
        if ar and (not isinstance(ar, str) or ar not in roles):
            errs.append(f"接口「{p}」的角色「{ar}」不在项目角色 {roles or '（没有角色）'} 里")
        if not isinstance(a.get("入参"), list) or not all(isinstance(i, str) and IDENT.match(i) for i in a["入参"]):
            errs.append(f"接口「{p}」要有「入参」：请求体字段名列表（没有就写 []）")
        used = _strs(a.get("用sql"), f"接口「{p}」的用sql", errs)
        for s in used:
            if s not in avail_sqls and s not in nset:
                errs.append(f"接口「{p}」的用sql「{s}」不存在：只能用已有的 sql {sorted(avail_sqls)[:40]}，或把它列在「新sql」里")
        rs = _strs(a.get("规则"), f"接口「{p}」的规则", errs)
        for h in rs:
            if h not in assigned:
                errs.append(f"接口「{p}」的规则「{h}」不是分给本文件的规则 {sorted(assigned)}")
        covered |= set(rs)
        out.append({"路径": p, "动作": an, "角色": ar, "入参": a.get("入参") if isinstance(a.get("入参"), list) else [], "用sql": used,
                    "规则": rs, "说明": str(a.get("说明") or "")})
    for h in sorted(set(assigned) - covered):
        errs.append(f"分给本文件的规则 {h} 没有落到任何接口的「规则」里")
    return {"接口": out, "新sql": news}, errs


def plan_ui(x, avail_paths):
    """avail_paths：项目里真实存在的接口路径（含 gen 的 CRUD）。"""
    o, err = _obj(x)
    if err:
        return None, [err]
    errs = []
    ps = o.get("页面")
    if not isinstance(ps, list) or not ps:
        errs.append("「页面」要是非空列表：[{\"名\":\"答题页\",\"说明\":\"…\",\"用接口\":[\"/attempt/answer\"],\"字段\":[\"given\"]}]")
        ps = []
    out, names = [], set()
    for p in ps:
        n = p.get("名") if isinstance(p, dict) else None
        if not isinstance(n, str) or not n.strip():
            errs.append("页面项要有「名」")
            continue
        if n in names:
            errs.append(f"页面名「{n}」重复")
        names.add(n)
        use = _strs(p.get("用接口"), f"页面「{n}」的用接口", errs)
        for u in use:
            if u not in avail_paths:
                errs.append(f"页面「{n}」的用接口「{u}」不存在：只能用已有的接口 {sorted(avail_paths)[:40]}")
        out.append({"名": n, "说明": str(p.get("说明") or ""), "用接口": use, "字段": _strs(p.get("字段"), f"页面「{n}」的字段", errs)})
    return {"页面": out}, errs
