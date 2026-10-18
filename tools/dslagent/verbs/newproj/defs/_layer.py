"""分层清单（--layered 模板第一步模型的输出）的解析、校验、拓扑序、文件计划。下划线开头，scan_verbs 不注册；
校验分层清单.py 是它的动词外壳，tools/dslagent/layered.py 直接 import 它。

清单格式（JSON 对象）：
{"模板":"default|full|private","角色":["teacher","student"],
 "规则":[{"号":"R1","文":"需求原句"}],
 "实体":[{"名":"quiz_state","说明":"…","关联":["question"]}],
 "查询":[{"实体":"quiz_state","sql":[{"名":"quiz_state_pick","参数":["learner"],"说明":"…"}],"规则":["R3"]}],
 "接口":[{"实体":"attempt","文件":"routes/attempt.zs","规则":["R4"],
          "接口":[{"路径":"/attempt/answer","动作":"attempt_answer","角色":"student","入参":["answer"],"用sql":["attempt_insert","mastery_bump"],"说明":"…"}]}],
 "界面":[{"文件":"ui/quiz.ui","实体":"quiz_state","用接口":["/quiz/start","/attempt/answer"]}]}
"""
import json
import os
import re

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```[ \t]*$", re.S)
TEMPLATES = ("default", "full", "private")
GEN_SQL_SUFFIX = ("list", "one", "insert", "update", "delete")      # gen 为每个实体自动生成的 sql / 接口
GEN_PATH_SUFFIX = ("list", "one", "create", "update", "delete")
CALLS_PLAN = 2
ROLE_HINT = re.compile(r"登录|登陆|账号|帐号|账户|角色|权限|(?:仅|只|只有|只许|只能|仅限)(?:由)?(?:老师|教师|学生|管理员)|(?:老师|教师|管理员)(?:才能|才可以|专属)|(?:老师|教师|学生|管理员)(?:端|账号)")
MAX_ENV = "NEWPROJ_LAYERED_MAX_FILES"


def max_files():
    try:
        return max(1, int(os.environ.get(MAX_ENV) or 60))
    except ValueError:
        return 60


def calls_cap(ents, qfiles, ifaces, uis):
    """2（清单）+ 实体 / 查询 / 界面 每个 ≤2 次（写 + 重写 1 次）+ 接口每个 ≤2 次（没有规则）或 ≤6 次（写 2 + 规则核对 + 规则重写 2 + 再核对 1）。
    ifaces：每个接口文件是否有规则的布尔列表。"""
    return CALLS_PLAN + 2 * (ents + qfiles + uis) + sum(6 if r else 2 for r in ifaces)


def parse(x):
    if isinstance(x, dict):
        return x, ""
    t = str(x or "").strip()
    m = FENCE.match(t)
    if m:
        t = m.group(1).strip()
    if not t:
        return None, "清单为空"
    try:
        v = json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")      # 模型偶尔在 JSON 前后加一句话
        if i < 0 or j <= i:
            return None, "清单不是合法 JSON"
        try:
            v = json.loads(t[i:j + 1])
        except ValueError as e:
            return None, f"清单不是合法 JSON：{e}"
    return (v, "") if isinstance(v, dict) else (None, "清单要是一个 JSON 对象")


def _list(obj, key, errs, what=None):
    v = obj.get(key)
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        errs.append(f"「{what or key}」要是列表")
        return []
    return v


def _strs(v, what, errs):
    if v in (None, ""):
        return []
    if not isinstance(v, list) or not all(isinstance(i, str) and i.strip() for i in v):
        errs.append(f"{what} 要是非空文本列表")
        return []
    return v


def topo(entities):
    """entities: [{名, 关联}] → (顺序, 环里的实体名列表)。关联在前；同层按清单顺序。"""
    names = [e["名"] for e in entities]
    deps = {e["名"]: [d for d in e.get("关联") or [] if d in names and d != e["名"]] for e in entities}
    order, done, left = [], set(), list(names)
    while left:
        ready = [n for n in left if all(d in done for d in deps[n])]
        if not ready:
            return order, left
        for n in ready:
            order.append(n)
            done.add(n)
            left.remove(n)
    return order, []


def gen_sqls(entity_names):
    return {f"{e}_{s}" for e in entity_names for s in GEN_SQL_SUFFIX}


def gen_paths(entity_names):
    return {f"/{e}/{s}" for e in entity_names for s in GEN_PATH_SUFFIX}


def validate(清单, 需求=""):
    """返回 {ok, errors(list), ...}；ok 时带 规则表、实体(拓扑序)、文件计划等给 layered 用。"""
    obj, err = parse(清单)
    if err:
        return {"ok": False, "errors": [err]}
    errs = []
    tpl = str(obj.get("模板") or "").strip()
    if tpl not in TEMPLATES:
        errs.append(f"模板「{tpl}」不对，只能是 default / full / private")
    roles = _strs(obj.get("角色"), "顶层「角色」", errs)
    for r in roles:
        if not SNAKE.match(r):
            errs.append(f"角色「{r}」要是英文小写 snake（如 teacher）")
    if len(set(roles)) != len(roles):
        errs.append("「角色」里有重复项")
    if roles and tpl != "private":
        errs.append("清单给了「角色」，模板必须是 private（登录注册靠 private 生成）")
    if not roles and str(需求 or "").strip() and ROLE_HINT.search(str(需求)):
        errs.append("需求里提到了登录 / 账号 / 角色 / 权限，清单顶层必须给「角色」（如 [\"teacher\",\"student\"]，注册默认角色放最后）并选 private 模板")

    # 规则
    rules = {}
    for i, r in enumerate(_list(obj, "规则", errs), 1):
        if not isinstance(r, dict) or not str(r.get("号") or "").strip() or not str(r.get("文") or "").strip():
            errs.append(f"规则第 {i} 项要是 {{号, 文}}，两个都不能空")
            continue
        h = str(r["号"]).strip()
        if h in rules:
            errs.append(f"规则号「{h}」重复")
        rules[h] = str(r["文"]).strip()

    # 实体
    ents, seen = [], set()
    for i, e in enumerate(_list(obj, "实体", errs), 1):
        n = e.get("名") if isinstance(e, dict) else None
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"第 {i} 个实体名「{n}」要是英文小写 snake（如 quiz_state）")
            continue
        if n in seen:
            errs.append(f"实体「{n}」重复")
            continue
        if n == "user" and tpl == "private":
            errs.append("private 模板的 user 实体由 gen 生成（带 role 列），清单里不要列 user")
            continue
        seen.add(n)
        ents.append({"名": n, "说明": str(e.get("说明") or ""), "关联": _strs(e.get("关联"), f"实体「{n}」的关联", errs)})
    if not ents:
        errs.append("「实体」不能为空：至少列一个实体")
    for e in ents:
        for d in e["关联"]:
            if d not in seen:
                errs.append(f"实体「{e['名']}」的关联「{d}」不在实体列表里")
            if d == e["名"]:
                errs.append(f"实体「{e['名']}」不能关联自己")
    order, cyc = topo(ents)
    if cyc:
        errs.append(f"实体关联有环，排不出顺序：{'、'.join(cyc)}（拆掉一个方向的关联）")
    gsql, gpath = gen_sqls(seen), gen_paths(seen)

    # 查询层
    queries, sqls, qents = [], {}, set()          # sqls: sql 名 → 所属实体
    for i, q in enumerate(_list(obj, "查询", errs), 1):
        en = q.get("实体") if isinstance(q, dict) else None
        if en not in seen:
            errs.append(f"查询第 {i} 项的实体「{en}」不在实体列表里")
            continue
        if en in qents:
            errs.append(f"实体「{en}」在「查询」里出现了不止一次，合并成一项")
            continue
        qents.add(en)
        items = []
        for s in q.get("sql") or []:
            sn = s.get("名") if isinstance(s, dict) else None
            if not isinstance(sn, str) or not SNAKE.match(sn):
                errs.append(f"实体「{en}」的 sql 名「{sn}」要是英文小写 snake")
                continue
            if sn != en and not sn.startswith(en + "_"):
                errs.append(f"sql 名「{sn}」要以实体名「{en}_」开头")
            if sn in gsql:
                errs.append(f"sql 名「{sn}」与 gen 自动生成的重名（{'/'.join(GEN_SQL_SUFFIX)} 五条不用写）")
            if sn in sqls:
                errs.append(f"sql 名「{sn}」重复")
            sqls[sn] = en
            items.append({"名": sn, "参数": _strs(s.get("参数"), f"sql「{sn}」的参数", errs), "说明": str(s.get("说明") or "")})
        queries.append({"实体": en, "sql": items, "规则": _strs(q.get("规则"), f"实体「{en}」查询项的规则", errs)})

    # 接口层
    ifaces, paths, acts, files = [], {}, set(), set()
    for i, it in enumerate(_list(obj, "接口", errs), 1):
        en = it.get("实体") if isinstance(it, dict) else None
        f = it.get("文件") if isinstance(it, dict) else None
        if en not in seen:
            errs.append(f"接口第 {i} 项的实体「{en}」不在实体列表里")
            continue
        if not isinstance(f, str) or not (f == f"routes/{en}.zs" or re.fullmatch(rf"routes/{re.escape(en)}_[a-z0-9_]+\.zs", f)):
            errs.append(f"接口文件「{f}」命名不合规，要是 routes/{en}.zs 或 routes/{en}_<后缀>.zs")
            continue
        if f in files:
            errs.append(f"接口文件「{f}」重复")
            continue
        files.add(f)
        items = []
        for a in it.get("接口") or []:
            if not isinstance(a, dict):
                errs.append(f"{f} 的接口项要是对象")
                continue
            p, an = a.get("路径"), a.get("动作")
            if not isinstance(p, str) or not p.startswith("/"):
                errs.append(f"{f} 的接口路径「{p}」要以 / 开头")
            elif p in paths or p in gpath:
                errs.append(f"接口路径「{p}」重复" + ("（与 gen 自动生成的 CRUD 路径冲突）" if p in gpath else ""))
            else:
                paths[p] = f
            if not isinstance(an, str) or not SNAKE.match(an):
                errs.append(f"{f} 的动作名「{an}」要是英文小写 snake")
            elif an in acts:
                errs.append(f"动作名「{an}」重复")
            else:
                acts.add(an)
            ar = a.get("角色")
            if ar not in (None, "") and (not isinstance(ar, str) or ar not in roles):
                errs.append(f"接口「{p}」的角色「{ar}」不在顶层「角色」{roles or '（没给）'} 里")
            if "入参" not in a or not isinstance(a.get("入参"), list) or not all(isinstance(x, str) and re.fullmatch(r"[A-Za-z_]\w*", x) for x in a["入参"]):
                errs.append(f"接口「{p}」要有「入参」：请求体字段名的列表（没有就写 []），参数核对靠它判断 sql 的 :参数 有没有来源")
            used = _strs(a.get("用sql"), f"接口「{p}」的用sql", errs)
            items.append({"路径": p, "动作": an, "角色": ar or "", "入参": a.get("入参") if isinstance(a.get("入参"), list) else [],
                          "用sql": used, "说明": str(a.get("说明") or "")})
        ifaces.append({"实体": en, "文件": f, "接口": items, "规则": _strs(it.get("规则"), f"{f} 的规则", errs)})
    for it in ifaces:       # 用sql 必须在查询层（或 gen 自带的五条）里
        for a in it["接口"]:
            for s in a["用sql"]:
                if s not in sqls and s not in gsql:
                    errs.append(f"接口「{a['路径']}」的用sql「{s}」不在「查询」层里（也不是 gen 自带的 <实体>_list/one/insert/update/delete）")

    # 界面层
    uis, ufiles = [], set()
    for i, u in enumerate(_list(obj, "界面", errs), 1):
        f = u.get("文件") if isinstance(u, dict) else None
        if not isinstance(f, str) or not re.fullmatch(r"ui/[a-z][a-z0-9_]*\.ui", f):
            errs.append(f"界面文件「{f}」命名不合规，要是 ui/<英文小写名>.ui")
            continue
        if f in ufiles:
            errs.append(f"界面文件「{f}」重复")
            continue
        ufiles.add(f)
        en = u.get("实体")
        if en not in (None, "") and en not in seen:
            errs.append(f"界面「{f}」的实体「{en}」不在实体列表里")
        use = _strs(u.get("用接口"), f"界面「{f}」的用接口", errs)
        for p in use:
            if p not in paths and p not in gpath:
                errs.append(f"界面「{f}」的用接口「{p}」不在「接口」层里（也不是 gen 自带的 /<实体>/list|one|create|update|delete）")
        uis.append({"文件": f, "实体": en or "", "用接口": use, "说明": str(u.get("说明") or "")})

    # 规则：每条至少分配到一个查询或接口项
    assigned = set()
    for item in queries + ifaces:
        for h in item["规则"]:
            if h not in rules:
                errs.append(f"规则号「{h}」没在顶层「规则」里")
            assigned.add(h)
    for h in rules:
        if h not in assigned:
            errs.append(f"规则 {h}「{rules[h][:30]}」没有分配到任何查询或接口项（在对应项的「规则」里写上 {h}）")

    n_files = len(order) + sum(1 for q in queries if q["sql"]) + len(ifaces) + len(uis)
    if n_files > max_files():
        errs.append(f"文件太多（{n_files} 个，上限 {max_files()}），请合并相近的")
    out = {"ok": not errs, "errors": errs, "模板": tpl, "角色": roles if not errs else [],
           "角色模板": "private" if roles and not errs else "", "数量": n_files,
           "调用上限": calls_cap(len(order), sum(1 for q in queries if q["sql"]), [bool(i["规则"]) for i in ifaces], len(uis))}
    if not errs:
        out.update(规则表=rules, 实体=[e for n in order for e in ents if e["名"] == n], 查询=queries, 接口=ifaces, 界面=uis,
                   sql归属=sqls, 路径归属=paths)
    return out
