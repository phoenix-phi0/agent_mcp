"""modular 的接口约定：约定的源头是「骨架文件」，直接落在真实路径上，不再是 JSON。

模型按模块写出四类骨架（头部是固定格式的声明，正文是一行占位）：
  queries/<名>.sql    头部 `-- 参数: a 必填, b 可选` `-- 返回: col1 col2 | 写入` `-- 作用: …`（另有 `-- 表:` `-- 用列:` `-- 规则:`），正文 `-- 待实现`
  scripts/<名>.zs     头部 `#@ 入参 learner level?` `#@ 出参 …` `#@ 写 表` `#@ 调用 scripts/x.zs a=… | sql y a=…` `#@ 动词 …` `#@ 错误 码 情形` `#@ 规则 R1` `#@ 作用 …`，正文 用包 + 返回 {"error":"未实现"}
  routes/<文件>.zs    真实的 `接口 POST /p 动作 a [角色 r]` 头行，下面 `#@ 请求 …` `#@ 调用 …` `#@ 响应 state.k lists.k messages` `#@ 错误 404 …` `#@ 规则 …` `#@ 作用 …`，正文占位 `返回 {"error":"未实现"} 501`，`结束`
  ui/<页>.ui          头部 `#@ 用接口 /p1 /p2` `#@ 字段 …`，正文最小可编译页面
`#@` 行引擎当注释忽略（`#` 开头的整行注释；sql 的 `--` 同理）。程序解析出的约定与 contract.validate_contract 吃的 dict 同形，校验后冻结（只存约定部分的快照），
实现＝填骨架：输出整份文件，约定部分（头行 / `#@` 行 / sql 头注释）必须与快照逐行一致，正文占位换成真实实现。
"""
import re

MARK = "待实现"
FILE_RE = re.compile(r"^===\s*(\S+?)\s*===\s*$")
HEAD_RE = re.compile(r"^接口\s+(\S+)\s+(/\S*)\s+动作\s+(\S+)(?:\s+角色\s+(\S+))?\s*$")
SQL_KEYS = ("参数", "返回", "作用", "表", "用列", "规则")
SQL_LINE = re.compile(r"^--\s*(参数|返回|作用|表|用列|规则)\s*[:：]\s*(.*)$")
SHARP = re.compile(r"^#@\s*(\S+)\s*(.*)$")
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
PLACE_FLOW = ['# ' + MARK, "用包 common", '返回 {"error":"未实现"}']
PLACE_ROUTE = ["  # " + MARK, "  用包 common", '  返回 {"error":"未实现"} 501']


def split_files(text):
    """模型输出 → ({路径: 内容}, 错误)。分隔行 `=== 路径 ===`；围栏忽略。"""
    files, errs, cur, buf = {}, [], None, []
    for raw in str(text or "").replace("\r\n", "\n").split("\n"):
        if raw.strip().startswith("```"):
            continue
        m = FILE_RE.match(raw.strip())
        if m:
            if cur is not None:
                files[cur] = "\n".join(buf).strip("\n") + "\n"
            cur, buf = m.group(1), []
            if cur in files:
                errs.append(f"文件「{cur}」写了两遍")
        elif cur is not None:
            buf.append(raw)
    if cur is not None:
        files[cur] = "\n".join(buf).strip("\n") + "\n"
    if not files:
        errs.append("没有 `=== 路径 ===` 分隔的文件块")
    return files, errs


def kind_of(rel):
    for pre, k in (("queries/", "sql"), ("scripts/", "flow"), ("routes/", "route"), ("ui/", "ui")):
        if rel.startswith(pre):
            return k
    return None


def stem(rel):
    return rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def is_skeleton(text):
    """还是骨架（正文占位没换掉）。"""
    return any(re.match(rf"^\s*(--|#)\s*{MARK}\s*$", l) for l in str(text or "").splitlines())


def _toks(v):
    v = v.strip()
    if v in ("", "无", "-"):
        return []
    return [t for t in re.split(r"[\s,，、]+", v) if t]


def _plist(v):
    """'a b? c' → [{名,要求}]。"""
    out = []
    for t in _toks(v):
        opt = t.endswith("?")
        out.append({"名": t.rstrip("?"), "要求": "可选" if opt else "必填"})
    return out


def _calls(vals, what, errs, rel):
    out = []
    for ln, raw, v in vals:
        toks = v.split()
        if toks and toks[0] == "sql":
            toks = toks[1:]
        elif toks and toks[0].startswith("scripts/"):
            toks = [toks[0].removeprefix("scripts/").removesuffix(".zs"), *toks[1:]]
        else:
            errs.append(f"{rel} 第 {ln} 行「{raw.strip()}」：调用 要写成 `scripts/<流程>.zs 键=…` 或 `sql <名> 键=…`")
            continue
        if not toks:
            errs.append(f"{rel} 第 {ln} 行「{raw.strip()}」：调用 后面缺名字")
            continue
        keys = []
        for t in toks[1:]:
            k = t.split("=", 1)[0].strip()
            if k:
                keys.append(k)
        out.append({"名": toks[0], "给": keys})
    return out


def _sharps(lines, rel):
    """lines：[(行号, 原行)] → ({键: [(行号, 原行, 值)…]}, 其它错误)。"""
    got, errs = {}, []
    for ln, raw in lines:
        m = SHARP.match(raw.strip())
        if m:
            got.setdefault(m.group(1), []).append((ln, raw, m.group(2).strip()))
    return got, errs


def _one(got, key):
    v = got.get(key) or []
    return v[0][2] if v else None


def _biz_flow(vals):
    out = []
    for _ln, _raw, v in vals:
        a, _, b = v.partition(" ")
        out.append({"情形": b.strip(), "返回": "" if a == "-" else a})
    return out


def _biz_if(vals):
    out = []
    for _ln, _raw, v in vals:
        a, _, b = v.partition(" ")
        out.append({"码": int(a) if a.isdigit() else a, "情形": b.strip()})
    return out


# ================================================================== 解析：四类骨架 → 约定 dict

def parse_sql(rel, text):
    errs, got = [], {}
    n = stem(rel)
    for ln, raw in enumerate(text.splitlines(), 1):
        m = SQL_LINE.match(raw.strip())
        if m:
            if m.group(1) in got:
                errs.append(f"{rel} 第 {ln} 行「{raw.strip()}」：头部「{m.group(1)}」写了两遍")
            got[m.group(1)] = m.group(2).strip()
    for k in ("参数", "返回"):
        if k not in got:
            errs.append(f"{rel}：头部缺 `-- {k}: …`（没有参数写 `-- 参数: 无`）")
    if errs:
        return None, errs
    ps = []
    for item in re.split(r"[,，]", got["参数"]):
        t = item.split()
        if not t or t == ["无"]:
            continue
        name = t[0].rstrip("?")
        ps.append({"名": name, "要求": t[1] if len(t) > 1 else ("可选" if t[0].endswith("?") else "必填")})
    ret = "写入" if got["返回"].strip() == "写入" else _toks(got["返回"])
    return {"名": n, "参数": ps, "返回": ret, "作用": "" if got.get("作用", "") == "无" else got.get("作用", ""),
            "表": _toks(got.get("表", "")), "用列": _toks(got.get("用列", "")), "规则": _toks(got.get("规则", ""))}, []


def parse_flow(rel, text):
    got, errs = _sharps(list(enumerate(text.splitlines(), 1)), rel)
    for k in ("入参", "出参"):
        if k not in got:
            errs.append(f"{rel}：缺 `#@ {k} …`（没有就写 `#@ {k} 无`）")
    if errs:
        return None, errs
    calls = _calls(got.get("调用") or [], "调用", errs, rel)
    if errs:
        return None, errs
    return {"名": stem(rel), "入参": _plist(_one(got, "入参")), "出参": _toks(_one(got, "出参")), "写哪些表": [t for _l, _r, v in got.get("写", []) for t in _toks(v)],
            "调": calls, "用动词": [t for _l, _r, v in got.get("动词", []) for t in _toks(v)], "业务错误": _biz_flow(got.get("错误") or []),
            "作用": _one(got, "作用") or "", "规则": [t for _l, _r, v in got.get("规则", []) for t in _toks(v)]}, []


def route_blocks(text):
    """[(头行号, 头行, [(行号, 行)…正文含 #@ 行])]：从 `接口 ` 头行起，到 `结束`（或下一个接口头 / 文件尾）。"""
    out, cur = [], None
    for ln, raw in enumerate(text.splitlines(), 1):
        if raw.startswith("接口 ") or raw.startswith("接口\t"):
            if cur:
                out.append(cur)
            cur = (ln, raw, [])
        elif cur is not None:
            if raw.strip() == "结束" and not raw.startswith(" "):
                out.append(cur)
                cur = None
            else:
                cur[2].append((ln, raw))
    if cur:
        out.append(cur)
    return out


def parse_route(rel, text):
    items, errs = [], []
    blocks = route_blocks(text)
    if not blocks:
        return [], [f"{rel}：没有 `接口 POST /路径 动作 名 [角色 x]` 头行"]
    for ln, head, body in blocks:
        m = HEAD_RE.match(head.strip())
        if not m:
            errs.append(f"{rel} 第 {ln} 行「{head.strip()}」：接口头行要写成 `接口 POST /路径 动作 动作名 [角色 x]`")
            continue
        if m.group(1) != "POST":
            errs.append(f"{rel} 第 {ln} 行「{head.strip()}」：方法一律 POST")
        got, _e = _sharps(body, rel)
        if "请求" not in got:
            errs.append(f"{rel} 第 {ln} 行「{head.strip()}」：缺 `#@ 请求 …`（没有请求字段写 `#@ 请求 无`）")
            continue
        calls = _calls(got.get("调用") or [], "调用", errs, rel)
        it = {"文件": stem(rel), "路径": m.group(2), "动作": m.group(3), "角色": m.group(4) or "", "请求字段": _plist(_one(got, "请求")),
              "调用": calls, "业务错误": _biz_if(got.get("错误") or []), "作用": _one(got, "作用") or "", "规则": [t for _l, _r, v in got.get("规则", []) for t in _toks(v)]}
        if "响应" in got:
            st, ls, msg = [], [], "否"
            for t in _toks(" ".join(v for _l, _r, v in got["响应"])):
                if t == "messages" or t == "messages=是":
                    msg = "是"
                elif t == "messages=否":
                    msg = "否"
                elif t.startswith("state."):
                    st.append(t[6:])
                elif t.startswith("lists."):
                    ls.append(t[6:])
                else:
                    errs.append(f"{rel} 第 {ln} 行「{head.strip()}」：#@ 响应 的项要写成 state.键 / lists.键 / messages，不认识「{t}」")
            it["响应"] = {"state": st, "lists": ls, "messages": msg}
        items.append(it)
    return items, errs


def parse_ui(rel, text):
    got, errs = _sharps(list(enumerate(text.splitlines(), 1)), rel)
    if "用接口" not in got:
        return None, [f"{rel}：缺 `#@ 用接口 /路径 …`（不用接口写 `#@ 用接口 无`）"]
    return {"页": stem(rel), "用接口": [t for _l, _r, v in got["用接口"] for t in _toks(v)], "字段": [t for _l, _r, v in got.get("字段", []) for t in _toks(v)]}, []


def extract(files):
    """{路径: 骨架文本} → (约定 dict {sql, 流程, 接口, 界面}, 错误列表)。路径不在四类目录里、文件名不合规也报。"""
    obj = {"sql": [], "流程": [], "接口": [], "界面": []}
    errs = []
    for rel in sorted(files):
        k, text = kind_of(rel), files[rel]
        ext = {"sql": ".sql", "flow": ".zs", "route": ".zs", "ui": ".ui"}.get(k)
        if k is None or not rel.endswith(ext) or rel.count("/") != 1:
            errs.append(f"文件路径「{rel}」不对：只能是 queries/<名>.sql、scripts/<名>.zs、routes/<文件>.zs、ui/<页>.ui")
            continue
        if k != "ui" and not SNAKE.match(stem(rel)):
            errs.append(f"文件名「{rel}」要是英文小写 snake")
        if k == "sql":
            it, e = parse_sql(rel, text)
            obj["sql"] += [it] if it else []
        elif k == "flow":
            it, e = parse_flow(rel, text)
            obj["流程"] += [it] if it else []
        elif k == "route":
            its, e = parse_route(rel, text)
            obj["接口"] += its
        else:
            it, e = parse_ui(rel, text)
            obj["界面"] += [it] if it else []
        errs += e
    return obj, errs


# ================================================================== 渲染：约定 → 规范骨架文件

def _pl(ps):
    return " ".join(p["名"] + ("?" if p["要求"] == "可选" else "") for p in ps) or "无"


def _wd(s):
    return re.sub(r"\s+", "_", str(s).strip()) or "-"


def _call_line(c):
    keys = " ".join(f"{k}=…" for k in c["给"])
    return (f"sql {c['名']}" if c.get("类") == "sql" else f"scripts/{c['名']}.zs") + (" " + keys if keys else "")


def render_sql(s):
    ps = ", ".join(p["名"] + " " + p["要求"] for p in s["参数"]) or "无"
    ret = "写入" if s["返回"] == "写入" else " ".join(s["返回"])
    return "\n".join([f"-- 参数: {ps}", f"-- 返回: {ret}", f"-- 作用: {' '.join(str(s['作用'] or '无').split())}", f"-- 表: {' '.join(s['表']) or '无'}",
                      f"-- 用列: {' '.join(s['用列']) or '无'}", f"-- 规则: {' '.join(s['规则']) or '无'}", "-- " + MARK]) + "\n"


def flow_head(f):
    L = [f"#@ 作用 {' '.join(str(f['作用'] or '无').split())}", f"#@ 入参 {_pl(f['入参'])}", f"#@ 出参 {' '.join(f['出参']) or '无'}"]
    if f["写哪些表"]:
        L.append("#@ 写 " + " ".join(f["写哪些表"]))
    L += [f"#@ 调用 {_call_line(c)}" for c in f["调"]]
    if f["用动词"]:
        L.append("#@ 动词 " + " ".join(f["用动词"]))
    L += [f"#@ 错误 {_wd(e['返回'])} {e['情形']}" for e in f["业务错误"]]
    if f["规则"]:
        L.append("#@ 规则 " + " ".join(f["规则"]))
    return L


def render_flow(f):
    return "\n".join([*flow_head(f), *PLACE_FLOW]) + "\n"


def route_head(a):
    r = a["响应"]
    resp = " ".join([*(f"state.{k}" for k in r["state"]), *(f"lists.{k}" for k in r["lists"]), *(["messages"] if r["messages"] == "是" else [])]) or "无"
    L = [f"接口 POST {a['路径']} 动作 {a['动作']}" + (f" 角色 {a['角色']}" if a["角色"] else ""), f"  #@ 作用 {' '.join(str(a['作用'] or '无').split())}", f"  #@ 请求 {_pl(a['请求字段'])}"]
    L += [f"  #@ 调用 {_call_line(c)}" for c in a["调用"]]
    L.append(f"  #@ 响应 {resp}")
    L += [f"  #@ 错误 {e['码']} {e['情形']}" for e in a["业务错误"]]
    if a["规则"]:
        L.append("  #@ 规则 " + " ".join(a["规则"]))
    return L


def render_route(items):
    L = []
    for a in items:
        L += [*route_head(a), *PLACE_ROUTE, "结束", ""]
    return "\n".join(L)


def render_ui(u, actions):
    """actions：路径 → 动作名。最小可编译页面：自定义界面 + 一个分组，里头放用到的远程动作按钮。"""
    L = ["#@ 用接口 " + (" ".join(u["用接口"]) or "无"), "#@ 字段 " + (" ".join(u["字段"]) or "无"), f"界面 自定义 {u['页']}", "  # " + MARK, "  分组 区 竖排"]
    for p in u["用接口"]:
        if actions.get(p):
            L.append(f"    动作 {actions[p]} 远程 {p.strip('/').replace('/', '_')}")
    L += ["  结束", "结束"]
    return "\n".join(L) + "\n"


def render(c, actions):
    """一个模块的约定 → {路径: 规范骨架文本}。"""
    out = {}
    for s in c["sql"]:
        out[f"queries/{s['名']}.sql"] = render_sql(s)
    for f in c["流程"]:
        out[f"scripts/{f['名']}.zs"] = render_flow(f)
    by = {}
    for a in c["接口"]:
        by.setdefault(a["文件"], []).append(a)
    for fl, its in by.items():
        out[f"routes/{fl}.zs"] = render_route(its)
    for u in c["界面"]:
        out[f"ui/{u['页']}.ui"] = render_ui(u, actions)
    return out


# ================================================================== 约定部分快照 / 逐行比对

def contract_part(rel, text):
    """文件里属于约定的行（规范化空白）：sql 头注释 / 流程的 `#@` 行 / 接口块的头行与 `#@` 行（按路径分组）/ 界面的 `#@` 行。返回 {分组键: [行…]}。"""
    k = kind_of(rel)
    norm = lambda s: " ".join(s.split())      # noqa: E731
    if k == "sql":
        return {"": [norm(l) for l in text.splitlines() if SQL_LINE.match(l.strip())]}
    if k in ("flow", "ui"):
        return {"": [norm(l) for l in text.splitlines() if l.strip().startswith("#@")]}
    out = {}
    for _ln, head, body in route_blocks(text):
        m = HEAD_RE.match(head.strip())
        out[m.group(2) if m else head.strip()] = [norm(head), *(norm(l) for _n, l in body if l.strip().startswith("#@"))]
    return out


def freeze(files):
    """骨架文件 → 快照 {路径: 约定部分的文本}（解析器能直接读回）。"""
    snap = {}
    for rel, text in files.items():
        part = contract_part(rel, text)
        snap[rel] = "\n\n".join("\n".join(ls) for _k, ls in sorted(part.items())) + "\n"
    return snap


def check_frozen(rel, text, snap_text):
    """实现的约定部分必须和冻结快照逐行一致；还留着占位也不行。返回问题列表。"""
    want = contract_part(rel, snap_text if kind_of(rel) not in ("route",) else _snap_to_route(snap_text))
    got = contract_part(rel, text)
    errs = []
    for k in sorted(set(want) - set(got)):
        errs.append(f"{rel} 约定部分缺{'「' + k + '」' if k else ''}：{want[k][0]} …（骨架的头行与 #@ 行不许删）")
    for k in sorted(set(got) - set(want)):
        errs.append(f"{rel} 多出约定里没有的{'「' + k + '」' if k else '约定行'}（骨架的头行与 #@ 行不许增）")
    for k in sorted(set(want) & set(got)):
        if want[k] != got[k]:
            a, b = want[k], got[k]
            i = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
            errs.append(f"{rel} 约定部分被改动{'（' + k + '）' if k else ''}：约定是「{a[i] if i < len(a) else '（没有这行）'}」，实现里是「{b[i] if i < len(b) else '（没有这行）'}」——头行与 #@ 行 / sql 头注释必须与骨架逐行一致")
    if is_skeleton(text):
        errs.append(f"{rel} 里还留着「{MARK}」占位，要换成真实实现")
    return errs


def _snap_to_route(snap_text):
    """路由快照（头行 + #@ 行，块之间空行隔开）还原成 route_blocks 能读的文本。"""
    out = []
    for blk in snap_text.strip().split("\n\n"):
        out += [blk, "结束", ""]
    return "\n".join(out)


def thaw(snap):
    """快照 {路径: 文本} → 约定 dict（和 extract 同形）。路由块里头行后的 #@ 行没有缩进也认。"""
    files = {rel: (_snap_to_route(t) if kind_of(rel) == "route" else t) for rel, t in snap.items()}
    return extract(files)


def cut_skeleton_blocks(text, paths):
    """去掉接口文件里 paths 这几个路径的骨架块（gen 的 CRUD 块原样留下）。"""
    lines = text.splitlines(keepends=True)
    drop = set()
    for ln, head, body in route_blocks(text):
        m = HEAD_RE.match(head.strip())
        if m and m.group(2) in paths:
            last = body[-1][0] if body else ln
            end = last + 1 if last < len(lines) and lines[last].strip() == "结束" and not lines[last].startswith(" ") else last
            drop.update(range(ln - 1, end))
            if end < len(lines) and not lines[end].strip():
                drop.add(end)
    out = "".join(l for i, l in enumerate(lines) if i not in drop)
    return out.rstrip("\n") + "\n" if out.strip() else ""
