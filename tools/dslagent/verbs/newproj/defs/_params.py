"""参数核对的实现（下划线开头，scan_verbs 不注册；参数核对.py 是动词外壳，layered.py 直接 import）。

静态读 zs：按「接口 METHOD /路径 …」切块，块内顺序扫描，维护「已定义变量」和「对象键」；对每个 查询 / 查一行 / 查一值 / 写库（具名参数 k=v）
和 查询表 / 查一行表 / 查一值表 / 写库表（参数表）调用，取 queries/<名>.sql 里的 :参数，逐个找来源。
db 动词的真实行为（verbs/db/_verbs.py bind）：具名参数只认调用处写的 k=v；参数表只认那个字典里的键；{request} 里是请求体字段 + 路由器注入的
current_user / current_role / auth_mode（+ 认证 身份 变量）。块里 设 过的普通变量不会自动绑进 SQL——kg_rebuild2 的 pass_line / fall_line
就是 zs 里 设 了变量却用 {request} 去写库，运行时缺参数 500。
"""
import json
import re

DB_NAMED = ("查询", "查一行", "查一值", "写库")
DB_TABLE = ("查询表", "查一行表", "查一值表", "写库表")
CALL = re.compile(r"^(?:设\s+\S+\s*=\s*)?(" + "|".join(sorted(DB_NAMED + DB_TABLE, key=len, reverse=True)) + r")\s+(\S+)\s+(\S+)(?:\s+(.*))?$")
ASSIGN = re.compile(r"^设\s+([^\s=]+)\s*=\s*(.*)$")
FOR = re.compile(r"^遍历\s+(\S+)\s+于\s+.*?(?:序号\s+(\S+))?\s*$")
HEAD = re.compile(r"^接口\s+(\w+)\s+(\S+)(.*)$")
VAR = re.compile(r"\{([^{}]+)\}")
PARAM = re.compile(r"(?<!:):([A-Za-z_]\w*)")
INJECTED_VARS = {"request", "current_user", "current_role", "auth_mode", "session", "run_mode"}
INJECTED_REQ = {"current_user", "current_role", "auth_mode"}
IDENTITY = re.compile(r"^认证\s+身份\s+(\w+)", re.M)


def sql_params(text):
    t = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    t = "\n".join(l.split("--", 1)[0] for l in t.splitlines())
    t = re.sub(r"'(?:[^']|'')*'", "''", t)
    return sorted(set(PARAM.findall(t)))


def declared(x):
    """接口声明：None（不严格）/ {路径: [入参…]} / 清单接口项列表 [{路径, 入参}…]（或带「接口」的文件项列表）。返回 (dict|None, 错误)。"""
    if x in (None, "", {}):
        return None, ""
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except ValueError as e:
            return None, f"接口声明不是 JSON：{e}"
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out[str(k)] = [str(i) for i in (v or [])]
    elif isinstance(x, list):
        for it in x:
            if not isinstance(it, dict):
                return None, "接口声明要是 {路径: [入参]} 或接口项列表"
            for a in (it.get("接口") if isinstance(it.get("接口"), list) else [it]):
                if isinstance(a, dict) and a.get("路径"):
                    out[str(a["路径"])] = [str(i) for i in (a.get("入参") or [])]
    else:
        return None, "接口声明要是 {路径: [入参]} 或接口项列表"
    return out, ""


def blocks(text):
    """[(method, path, 起始行号, [(行号, 行)…])…]；块到下一个顶格「接口」或顶格「结束」为止。"""
    out, cur = [], None
    for i, line in enumerate(text.splitlines(), 1):
        m = HEAD.match(line)
        if m:
            cur = (m.group(1), m.group(2), i, [])
            out.append(cur)
            continue
        if cur is not None:
            if line.startswith("结束"):
                cur = None
            else:
                cur[3].append((i, line))
    return out


SVC_MODULE = re.compile(r"^\s*业务\s+(\S+)")
SVC_FUNC = re.compile(r"^(\s*)(?:公开\s+)?函数\s+(\S+)((?:\s+[^\s#]+)*)\s*(?:#.*)?$")


def service_blocks(text):
    """业务文件（services/<模块>.zs）：返回 ([(\"函数\", \"模块.函数\", 起始行号, [(行号, 行)…])…], {模块.函数: [入参…]})；
    不是业务文件返回 None。函数体到和「函数」同缩进的「结束」为止。入参（去掉可选的 ?）就是函数体里已定义的变量。"""
    lines = text.splitlines()
    mod = next((m.group(1) for m in (SVC_MODULE.match(l) for l in lines) if m), None)
    if mod is None:
        return None
    out, decl, cur, indent = [], {}, None, ""
    for i, line in enumerate(lines, 1):
        if cur is not None:
            if line.strip() == "结束" and line[:len(line) - len(line.lstrip())] == indent:
                cur = None
            else:
                cur[3].append((i, line))
            continue
        m = SVC_FUNC.match(line)
        if m:
            name = f"{mod}.{m.group(2)}"
            decl[name] = [t.rstrip("?") for t in m.group(3).split()]
            cur = ("函数", name, i, [])
            indent = m.group(1)
            out.append(cur)
    return out, decl


def _root(ref):
    ref = ref.strip()
    ref = ref.split(" 或", 1)[0].strip()
    return re.split(r"[.\s]", ref, 1)[0]


def _lit_keys(s):
    return set(re.findall(r'"(\w+)"\s*:', s))


def check_text(text, rel, qdir, decl, identity=()):
    """返回 ([问题…], 检查的调用数)。qdir：queries 目录（Path）；decl：declared() 的结果；identity：认证 身份 变量名。"""
    errs, n = [], 0
    inj_vars = INJECTED_VARS | set(identity)
    inj_req = INJECTED_REQ | set(identity)
    # 业务文件：每个函数当一个块，入参是函数体里已定义的变量（函数是独立作用域，没有 {request} 和路由器注入的变量）
    svc = service_blocks(text)
    service = svc is not None
    if service:
        block_list, decl = svc
        inj_vars, inj_req = set(), set()
    else:
        block_list = blocks(text)
    for method, path, ln0, lines in block_list:
        where = f"{rel}:{ln0} " + (f"函数 {path}" if service else f"接口 {path}")
        strict = decl is not None
        fields = set(decl.get(path, [])) if strict else set()
        defined = set(inj_vars) | fields
        # 对象名 → 已知键；不在里面的对象 = 键未知（宽松）。业务函数里没有 request
        objs = {} if service else {"request": set(fields) | inj_req}
        opaque = set()                                  # 被整体赋成动词结果等的变量：键未知，之后 设 x.k 也不算数
        for ln, raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = CALL.match(line)
            if m:
                verb, _db, name, rest = m.group(1), m.group(2), m.group(3).removesuffix(".sql"), (m.group(4) or "").strip()
                f = qdir / f"{name}.sql"
                if not f.is_file():
                    errs.append(f"{where}（第 {ln} 行）引用了不存在的 sql「{name}」（queries/ 下没有 {name}.sql）")
                else:
                    n += 1
                    need = sql_params(f.read_text(encoding="utf-8", errors="replace"))
                    if verb in DB_NAMED:
                        toks = rest.split()
                        given = {}
                        for t in toks:
                            k, sep, v = t.partition("=")
                            if sep:
                                given[k.strip()] = v
                        miss = [p for p in need if p not in given]
                        if miss:
                            errs.append(f"{where}（第 {ln} 行）{verb} {name} 缺少参数 {'、'.join(':' + p for p in miss)}（具名参数只认调用处写的 k={{v}}；"
                                        f"这条 sql 要 {'、'.join(need)}）")
                        for k, v in given.items():
                            for ref in VAR.findall(v):
                                if _root(ref) not in defined and " 或" not in ref:
                                    errs.append(f"{where}（第 {ln} 行）{name} 的参数 {k}={{{ref}}} 没有来源（前面没 设 过 {_root(ref)}，也不是接口「入参」）")
                    else:
                        arg = rest.split()[0] if rest.split() else ""
                        keys, label = None, arg
                        vm = re.fullmatch(r"\{([^{}\s]+)\}", arg)
                        if vm:
                            obj = vm.group(1)
                            if obj in objs and (obj != "request" or strict):
                                keys = objs[obj]
                            elif obj == "request" and not service:
                                keys = None                        # 没给接口声明：请求体字段未知，不判
                            elif obj not in defined:
                                errs.append(f"{where}（第 {ln} 行）{verb} {name} 的参数表 {{{obj}}} 前面没有 设 过")
                        elif arg.startswith("{"):
                            keys = _lit_keys(rest)
                        if keys is not None:
                            miss = [p for p in need if p not in keys]
                            if miss:
                                src = "接口「入参」" + (f"{sorted(fields)}" if fields else "为空") + " + 路由器注入的 current_user/current_role/auth_mode" if label == "{request}" else f"参数表 {label}"
                                errs.append(f"{where}（第 {ln} 行）{verb} {name} {label} 缺少参数 {'、'.join(':' + p for p in miss)}"
                                            f"（{src} 里没有；这条 sql 要 {'、'.join(need)}。用 设 变量 不会绑进 sql：要么把值写进 {label} 的字段"
                                            f"（设 {label.strip('{}')}.{miss[0]} = …），要么改用具名参数 {miss[0]}=…，要么让界面传这个字段并写进接口「入参」）")
            a = ASSIGN.match(line)
            if a:
                target = a.group(1)
                head = target.split(".", 1)[0]
                defined.add(head)
                if "." in target:
                    key = target.split(".", 1)[1].split(".")[0]
                    if head in objs:
                        objs[head].add(key)
                    elif head not in inj_vars and head not in fields and head not in opaque:
                        objs.setdefault(head, set()).add(key)      # 对象在这里第一次出现：键逐个 设 出来
                else:
                    rhs = a.group(2).strip()
                    if rhs.startswith("{") and '"' in rhs:
                        objs[head] = _lit_keys(rhs)
                    elif head != "request":
                        objs.pop(head, None)                       # 重新赋值（动词结果等）：键未知
                        opaque.add(head)
            fm = FOR.match(line)
            if fm:
                defined.add(fm.group(1))
                if fm.group(2):
                    defined.add(fm.group(2))
    return errs, n


def identity_vars(root):
    """项目 routes 里 认证 身份 声明的变量名。"""
    out = set()
    d = root / "routes"
    if d.is_dir():
        for f in d.rglob("*.zs"):
            out |= set(IDENTITY.findall(f.read_text(encoding="utf-8", errors="replace")))
    return out
