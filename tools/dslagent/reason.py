"""执行中的小分支交给逻辑规则：Python 只算事实，rules/<名>.dl（datalog.Datalog）决定动作。

    from tools.dslagent import reason as R
    R.setup(项目, R.all_files(项目), 任务原文)       # 开局快照（写 / 删文件的安全约束要用）
    R.check("写入", 项目, "a.json", 内容)             # → "" 放行，否则拦截原因

这里是 v2 也用的部分：规则求值 infer、规则 3 安全约束（安全.dl：写 / 删文件之前，删仍被引用或没等价迁移的源数据、覆盖没点名且与
开局快照不等价的数据文件、写改删测试、越出项目 → 拦）、done_items（从任务文本机械抽出点名的产物，engine=auto 判定也用）、
开局快照 setup / all_files / restore。
旧路径专用的（规则 1 测试变化、规则 2 完成核对的检查、退回规划前回滚）在 legacy/reason_rules.py，规则文件在 legacy/rules/
（rules() 两处都找）。动词 推理（verbs/code/defs/推理.py）把规则接进 DSL。
开关：DSLAGENT_RULES=0 关（写删动词和旧路径都看它）。
"""
import ast
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

sys.modules.setdefault("dslagent_reason", sys.modules[__name__])
RULES_DIR = Path(__file__).resolve().parent / "rules"
LEGACY_RULES_DIR = Path(__file__).resolve().parent / "legacy" / "rules"      # 旧路径的规则文件（测试变化.dl、完成核对.dl）
DATA_EXT = (".json", ".csv", ".tsv", ".txt", ".yaml", ".yml", ".ini", ".toml")
STATE = {"snap": None, "task": "", "root": None, "log": [], "fires": []}
_CACHE = {}

REASONS = {
    "all_pass": "测试全过", "more_fail": "失败变多：撤回本次改动，带新失败重问",
    "same_err2": "同一错误连续 2 次：升级（交回上层退回规划或放弃）", "less_fail": "失败变少：保留本次改动继续",
    "set_changed": "失败集合换了：保留改动，带新失败重问", "no_change": "失败不变：带当前失败重问",
    "more_fail_no_undo": "失败变多但没法撤回：带新失败重问",
    "tests_fail": "测试没全过，不算完成", "all_met": "任务点名的产物逐条核对都满足",
    "unmet": "有点名的产物没满足：带未满足项再做一轮", "unmet_after_redo": "补做一轮后仍不满足：交模型对照任务确认一次",
    "unmet_final": "仍有未满足项，不算完成",
    "outside": "路径出了项目目录", "test_file": "不许改/删 tests/ 下的文件", "absent": "文件本来就不存在",
    "still_referenced": "代码仍依赖它——先把读取改到新文件、确认不再引用再删",
    "no_new_data": "还没生成替代它的新数据文件——先迁移（新建并核对内容）再删源数据",
    "records_mismatch": "新数据文件的记录数和源文件对不上，等价性检查没过",
    "equal_snapshot": "写回的内容与开局快照一致", "overwrite_data": "要覆盖开局就有的数据文件，但任务没要求改它，且新内容与开局快照不等价",
    "regress_dirty": "回归已坏（原本通过的测试现在失败）：退回规划前先回滚到开局快照", "ok": "放行",
}


def enabled():
    return os.environ.get("DSLAGENT_RULES", "1") not in ("0", "off", "否")


def _datalog_mod():
    try:
        from . import datalog as D
        return D
    except ImportError:          # 动词 推理 按文件路径单独加载本模块（没有包）：同目录的 datalog.py 也按路径加载
        import importlib.util
        m = sys.modules.get("dslagent_datalog")
        if m is None:
            spec = importlib.util.spec_from_file_location("dslagent_datalog", Path(__file__).resolve().parent / "datalog.py")
            m = importlib.util.module_from_spec(spec)
            sys.modules["dslagent_datalog"] = m
            spec.loader.exec_module(m)
        return m


def rules(name):
    name = name[:-3] if name.endswith(".dl") else name
    if name not in _CACHE:
        f = RULES_DIR / f"{name}.dl"
        if not f.is_file():
            f = LEGACY_RULES_DIR / f"{name}.dl"
        _CACHE[name] = _datalog_mod().parse_rules(f.read_text(encoding="utf-8"))
    return _CACHE[name]


def infer(name, facts):
    """facts：{谓词: 值 或 值列表}（值都按字符串）。返回优先级最高的 decide。"""
    name = name[:-3] if name.endswith(".dl") else name
    dl = _datalog_mod().Datalog(rules(name))
    for k, v in facts.items():
        for x in (v if isinstance(v, (list, tuple, set)) else [v]):
            dl.add(k, x if isinstance(x, str) else ("yes" if x is True else "no" if x is False else str(x)))
    got = dl.run().get("decide") or set()
    if not got:
        return {"action": "", "code": "", "reason": "没有规则命中", "rule": name}
    a, p, code = sorted(got, key=lambda t: (-int(t[1]), t[0]))[0]
    d = {"action": a, "prio": int(p), "code": code, "reason": REASONS.get(code, code), "rule": name}
    STATE["fires"].append({"rule": name, "action": a, "code": code})
    _log({"rule": name, "action": a, "code": code, "facts": {k: v for k, v in facts.items() if not isinstance(v, (list, set))}})
    return d


def _log(rec):
    st = os.environ.get("DSLAGENT_STATE")
    if st:
        try:
            with open(Path(st) / "rules_log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass


# ============================================================ 规则 1 测试变化

# ============================================================ 规则 2 完成前核对

PATH_RE = re.compile(r"(?<![\w./-])((?:[\w-]+/)*[\w-]+\.(?:py|json|csv|tsv|md|txt|yaml|yml|toml|ini))(?![\w])")
ID_RE = r"[A-Za-z_]\w*"
SEP = "。；;\n"
BUILTIN = set(dir(__builtins__) if isinstance(__builtins__, dict) is False else __builtins__) | {
    "ValueError", "KeyError", "IndexError", "TypeError", "print", "len", "str", "int", "float", "dict", "list"}


def _clause_after(t, e):
    m = re.search(r"[，,。；;\n]", t[e:])
    return t[e:e + (m.start() if m else len(t) - e)]


def _good_id(x):
    last = x.split(".")[-1]
    return ("_" in last.strip("_") or re.search(r"[A-Z][a-z]+[A-Z]", last)) and last not in BUILTIN


def _resolve(name, files):
    if "/" in name:
        return name
    hits = [k for k in files if Path(k).name == name and not k.startswith(("tests/", "test/"))]
    return hits[0] if len(hits) == 1 else None


def _top_keys(t, i):
    """从 t[i]='{' 起抽第一层的 "键": 。"""
    depth, keys, j = 0, [], i
    while j < len(t):
        c = t[j]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                break
        elif c == '"' and depth == 1:
            m = re.match(r'"([^"\n]{1,40})"\s*:', t[j:])
            if m:
                keys.append(m.group(1))
                j += m.end()
                continue
            m = re.match(r'"[^"\n]*"', t[j:])
            j += m.end() if m else 1
            continue
        j += 1
    return keys


def done_items(task, files):
    """从任务文本机械抽取点名的产物（只取高置信的）。files：开局文件名集合（解析裸文件名用）。
    返回 [{kind: exists|absent|unchanged|def|forbid|keys|lines|import, ...}]"""
    t = task or ""
    items, seen = [], set()

    def add(**it):
        k = json.dumps(it, ensure_ascii=False, sort_keys=True)
        if k not in seen:
            seen.add(k)
            items.append(it)

    for m in re.finditer(r"在\s*((?:[\w-]+/)+)\s*下\s*新建\s*([\w-]+\.\w+)", t):
        add(kind="exists", path=m.group(1) + m.group(2))
    new_json = []
    for m in PATH_RE.finditer(t):
        name, s, e = m.group(1), m.start(), m.end()
        pre = t[max(0, s - 10):s]
        pre = re.split(r"[。；;\n，,]", pre)[-1]
        after = _clause_after(t, e)
        if re.search(r"(不要动|别动|不要改|别改|不许改|别去改|保持不变)", after) and not re.search(r"新建|删", after):
            rel = _resolve(name, files)
            if rel and rel in files:
                add(kind="unchanged", path=rel)
            continue
        if re.search(r"删掉|删除", pre) or re.match(r"\s*(直接|也)?删(掉|除)", after):
            rel = _resolve(name, files)
            if rel:
                add(kind="absent", path=rel)
            continue
        if re.search(r"新建|新文件|生成|写一个|写个", pre):
            rel = name if "/" in name else (name if "根目录" in pre else None)
            if rel and rel not in files:
                add(kind="exists", path=rel)
                if rel.endswith(".json"):
                    new_json.append((rel, e))
    for rel, e in new_json:
        seg = t[e:e + 400]
        b = seg.find('{"')
        para_end = seg.find("\n\n")
        if b >= 0 and (para_end < 0 or b < para_end) and "结构" in seg[:b]:
            keys = _top_keys(seg, b)
            if keys and all(re.fullmatch(ID_RE, k) for k in keys):
                add(kind="keys", path=rel, keys=keys)
    if len(new_json) == 1:
        ks = re.findall(r"^\s*-\s*([a-z_][a-z0-9_]*)\s*[：:]", t, re.M)
        if len(ks) >= 2:
            add(kind="keys", path=new_json[0][0], keys=ks)
    for m in re.finditer(rf"({ID_RE}(?:\.{ID_RE})?)\(", t):
        x = m.group(1)
        if _good_id(x) and not t[max(0, m.start() - 6):m.start()].endswith(("from ", "import ")):
            add(kind="def", name=x.split(".")[-1])
    for m in re.finditer(rf"(?:改叫|叫做|名字叫|改名为|改成叫|换个名字叫|叫|定义)\s*({ID_RE})", t):
        if _good_id(m.group(1)):
            add(kind="def", name=m.group(1))
    for m in re.finditer(rf"((?:[\w-]+/)+)\s*下[^{SEP}]{{0,24}}?(?:不能再出现|不能出现|不许出现|不得出现)\s*({ID_RE})", t):
        add(kind="forbid", dir=m.group(1), name=m.group(2))
    for m in re.finditer(rf"([\w/-]+\.py)[^{SEP}]{{0,40}}?[，,]?\s*整个文件[^{SEP}]{{0,8}}?(\d+)\s*行以内", t):
        rel = _resolve(m.group(1), files)
        if rel:
            add(kind="lines", path=rel, max=int(m.group(2)))
    for m in re.finditer(rf"from\s+([\w.]+)\s+import\s+({ID_RE})", t):
        add(kind="import", mod=m.group(1), name=m.group(2))
    forb = {it["name"] for it in items if it["kind"] == "forbid"}
    gone = {Path(it["path"]).name for it in items if it["kind"] == "absent"}
    return [it for it in items if not (it["kind"] == "def" and it["name"] in forb)
            and not (it["kind"] == "exists" and Path(it["path"]).name in gone)]


def _src_files(root):
    root = Path(root)
    for f in root.rglob("*.py"):
        r = str(f.relative_to(root))
        if "__pycache__" in f.parts or any(p.startswith(".") for p in f.relative_to(root).parts) or _is_test(r):
            continue
        yield r, f


# ============================================================ 规则 3 安全约束

def setup(root, snap, task):
    """开局设：snap 开局快照 {相对路径: bytes}（all_files）、task 任务原文。"""
    STATE.update(root=str(Path(root).resolve()), snap=snap, task=task or "", log=[], fires=[])


def all_files(root):
    root = Path(root)
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not any(x.startswith(".") for x in p.relative_to(root).parts)}


def _is_test(rel):
    parts = Path(rel).parts
    return bool(parts) and (parts[0] in ("tests", "test") or Path(rel).name.startswith("test_") or Path(rel).name == "conftest.py")


def _records(rel, data):
    try:
        t = data.decode("utf-8") if isinstance(data, bytes) else data
        if rel.endswith((".csv", ".tsv")):
            rows = list(csv.reader(io.StringIO(t), delimiter="\t" if rel.endswith(".tsv") else ","))
            return max(0, len([r for r in rows if any(c.strip() for c in r)]) - 1)
        if rel.endswith(".json"):
            j = json.loads(t)
            if isinstance(j, list):
                return len(j)
            if isinstance(j, dict):
                for v in j.values():
                    if isinstance(v, list):
                        return len(v)
                return len(j)
    except Exception:
        return None
    return None


def _mentioned(rel):
    t = STATE.get("task") or ""
    name = Path(rel).name
    if not (rel in t or name in t):
        return False
    return not re.search(re.escape(name) + r"[^。；\n]{0,6}(不要动|不要改|别动|保持不变|不许改)", t)


def safety_facts(op, root, path, content=None):
    """op：删除/写入/改写 → 事实 + 细节（引用方等）。"""
    root = Path(root).resolve()
    p = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    try:
        rel = str(p.relative_to(root))
    except ValueError:
        return {"op": "delete" if op == "删除" else "write", "outside": True}, {"rel": str(path)}
    o = "delete" if op == "删除" else "write"
    snap = STATE.get("snap")
    f = {"op": o, "outside": False, "is_test": _is_test(rel), "exists": p.exists(),
         "data_file": rel.endswith(DATA_EXT) and not rel.endswith(".py"), "has_snap": snap is not None}
    extra = {"rel": rel}
    if o == "delete" and p.exists():
        name, stem, users = Path(rel).name, Path(rel).stem, []
        for r, fp in _src_files(root):
            s = fp.read_text(encoding="utf-8", errors="ignore")
            if re.search(re.escape(name), s) or (rel.endswith(".py") and r != rel and re.search(rf"\b{re.escape(stem)}\b", s)):
                users.append(r)
        f["referenced"] = bool(users)
        extra["users"] = users
        if snap is not None and f["data_file"]:
            new = [k for k in all_files(root) if k not in snap and k.endswith(DATA_EXT) and not _is_test(k)]
            f["new_data"] = bool(new)
            n0 = _records(rel, p.read_bytes())
            f["records_match"] = n0 is None or any(_records(k, (root / k).read_bytes()) == n0 for k in new)
            extra.update(new=new, n0=n0)
    if o == "write":
        in_snap = snap is not None and rel in snap
        f["in_snap"] = in_snap
        if in_snap:
            data = content.encode("utf-8") if isinstance(content, str) else content
            f["equal_snap"] = data is not None and data == snap[rel]
            f["mentioned"] = _mentioned(rel)
    return f, extra


def check(op, root, path, content=None):
    """返回 ''（放行）或拦截原因（并记进 STATE['log']）。先过范围闸（scope.guard，包声明的允许写 / 删路径）；关掉规则时只做越界/测试文件检查。"""
    import importlib
    _SC = importlib.import_module("tools.dslagent.scope")      # 动词里可能是按文件路径单独加载的本模块，不用相对 import
    why = _SC.guard(path if not os.path.isabs(str(path)) else os.path.relpath(str(path), str(root)))
    if why:
        STATE["log"].append({"op": op, "file": str(path), "why": why, "code": "out_of_scope"})
        return why
    f, extra = safety_facts(op, root, path, content)
    if not enabled():
        if f.get("outside") or f.get("is_test"):
            return f"{op} {extra['rel']}：{'路径出了项目目录' if f.get('outside') else '不许改/删测试文件'}"
        return ""
    d = infer("安全", f)
    if d["action"] != "block":
        return ""
    why = d["reason"]
    if d["code"] == "still_referenced":
        why = f"新代码仍依赖它（{'、'.join(extra['users'][:3])} 里还引用 {Path(extra['rel']).name}）——先把读取改到新文件、确认不再引用再删"
    elif d["code"] == "records_mismatch":
        why = f"新数据文件（{'、'.join(extra['new'][:3])}）的记录数和源文件（{extra['n0']} 条）对不上，等价性检查没过"
    STATE["log"].append({"op": op, "file": extra["rel"], "why": why, "code": d["code"]})
    return f"安全约束拦下 {op} {extra['rel']}：{why}"


def restore(root, snap):
    """把项目恢复到快照（非测试文件）：快照里有的写回，快照外新增的删掉。"""
    root = Path(root)
    cur = all_files(root)
    for k in cur:
        if k not in snap and not _is_test(k):
            (root / k).unlink()
    for k, v in snap.items():
        if not _is_test(k) and cur.get(k) != v:
            (root / k).parent.mkdir(parents=True, exist_ok=True)
            (root / k).write_bytes(v)
