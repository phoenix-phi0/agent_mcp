"""gen 相关的实际工作（进程内或被 _gen.run_op 当脚本在 .venv python 里跑：python -I _gencore.py <仓库根> < {op,args}）。
每个函数返回 dict，失败不抛。"""

import json
import re
import sqlite3
import sys
from pathlib import Path

MSG_CAP = 1500


def _gen_errors():
    from gen.project import ProjectError
    from tools.dsl import DSLError
    return ProjectError, DSLError


def generate(root, tpl="full", only=None, force=False):
    from gen import project as P
    PE, _ = _gen_errors()
    root = Path(root)
    log = []
    try:
        log += P.init(root, sample=False)
        if tpl == "private":
            log += P.add_auth(root)
            ents = P.load_entities(root)
            log += P.generate(root, "private", only=only or None, force=force)
            rest = [e.name for e in ents if "owner" not in [f.name for f in e.fields] and (not only or e.name in only)]
            if rest:
                log += P.generate(root, "full", only=rest, force=force)
        else:
            log += P.generate(root, tpl, only=only or None, force=force)
        log.append(P.ensure_db(root))
    except PE as e:
        return {"ok": "否", "msg": str(e)[:MSG_CAP]}
    except Exception as e:  # noqa: BLE001  模板缺失等也要变成 msg
        return {"ok": "否", "msg": f"{type(e).__name__}: {e}"[:MSG_CAP]}
    return {"ok": "是", "msg": "\n".join(x.rstrip() for x in log)[:MSG_CAP]}


def dup_routes(root):
    seen = {}
    for f in sorted((Path(root) / "routes").rglob("*.zs")):
        for m in re.finditer(r"^接口\s+(\w+)\s+(\S+)", f.read_text(encoding="utf-8"), re.M):
            seen.setdefault(m.groups(), []).append(str(f.relative_to(root)))
    return [f"接口 {k[0]} {k[1]} 重复出现在 {'、'.join(v)}" for k, v in seen.items() if len(v) > 1]


def check_project(root):
    from gen import project as P
    from tools.entity import parse, validate
    PE, DE = _gen_errors()
    root = Path(root)
    errs = []
    try:
        ents = parse(P.entities_text(root))
        errs += validate(ents)
    except Exception as e:  # noqa: BLE001
        errs.append(f"实体：{e}")
    errs += dup_routes(root)
    if not errs:
        try:
            P.build(root)
        except (PE, DE) as e:
            errs.append(f"build：{e}")
        except Exception as e:  # noqa: BLE001
            errs.append(f"build：{type(e).__name__}: {e}")
    if not errs:
        try:
            P.make_app(root)
        except Exception as e:  # noqa: BLE001  DSLError / 脚本语法 / 缺依赖
            errs.append(f"路由加载：{type(e).__name__}: {e}")
    return {"ok": "否" if errs else "是", "msg": ("；".join(errs) if errs else "通过")[:MSG_CAP]}


QREF = re.compile(r"^[^#\n]*?\b(?:查询|查一行|查一值)表?\s+\S+\.db\s+([^\s{=]+)", re.M)


def missing_queries(root):
    """routes/、scripts/ 下 .zs 里 查询 / 查一行 / 查一值 引用的 queries/<名>.sql 不存在的，返回「文件:行 引用了不存在的查询 名」列表。"""
    root = Path(root)
    have = {f.stem for f in (root / "queries").glob("*.sql")} if (root / "queries").is_dir() else None
    if have is None:
        return []
    out = []
    for d in ("routes", "scripts"):
        for f in sorted((root / d).rglob("*.zs")) if (root / d).is_dir() else []:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = QREF.match(line)
                name = m.group(1) if m else ""
                if name and name != "表" and name.removesuffix(".sql") not in have and not name.startswith("{"):
                    out.append(f"{f.relative_to(root)}:{i} 引用了不存在的查询 {name}（queries/ 下没有 {name.removesuffix('.sql')}.sql）")
    return out


IGNORE = ("__pycache__", "*.db", "*.db-*", "sessions", ".venv", ".git", "node_modules")


def dsl_verify(root, ui_files=()):
    """改完后的 DSL 验收：把项目拷到临时目录（不碰工作区的 app.db），依次 实体解析+校验 → build → ensure_db（新库）→ make_app
    （含重复接口）→ 对 ui_files（项目内相对路径）逐个跑 ui 检查。返回 {ok, errors: [{步, msg}], msg}；碰到第一个挂掉的链上步骤就停，ui 检查另外跑。"""
    import shutil
    import tempfile
    from gen import project as P
    from tools.entity import parse, validate
    from tools.ui import check as ui_check
    PE, DE = _gen_errors()
    root = Path(root)
    errs = []
    tmp = Path(tempfile.mkdtemp(prefix="dslverify_"))
    try:
        p = tmp / root.name
        shutil.copytree(root, p, ignore=shutil.ignore_patterns(*IGNORE))

        def chain():
            try:
                errs.extend({"步": "实体", "msg": m} for m in validate(parse(P.entities_text(p))))
            except Exception as e:  # noqa: BLE001
                errs.append({"步": "实体", "msg": f"{type(e).__name__}: {e}"})
            if errs:
                return
            try:
                P.build(p)
            except Exception as e:  # noqa: BLE001  ProjectError / DSLError / 缺依赖
                errs.append({"步": "build", "msg": f"{type(e).__name__}: {e}"})
                return
            try:
                P.ensure_db(p)
            except Exception as e:  # noqa: BLE001
                errs.append({"步": "建库", "msg": f"{type(e).__name__}: {e}"})
                return
            errs.extend({"步": "接口", "msg": m} for m in dup_routes(p))
            errs.extend({"步": "sql引用", "msg": m} for m in missing_queries(p))
            if errs:
                return
            try:
                P.make_app(p)
            except Exception as e:  # noqa: BLE001
                errs.append({"步": "路由加载", "msg": f"{type(e).__name__}: {e}"})
        chain()
        for rel in ui_files or ():
            f = p / rel
            if not f.is_file():
                continue
            try:
                out = ui_check(f.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                out = f"语法错误：{type(e).__name__}: {e}"
            bad = [ln for ln in out.splitlines() if ln.startswith(("语法错误", "没有解析到"))]
            if bad and not any(e["步"] == "ui" and e.get("文件") == rel for e in errs):
                errs.append({"步": "ui", "文件": rel, "msg": "；".join(bad)})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for e in errs:
        e["msg"] = e["msg"].replace(str(tmp / root.name) + "/", "").replace(str(tmp / root.name), ".")
    return {"ok": "否" if errs else "是", "errors": errs,
            "msg": ("；".join(f"{e['步']}：{e['msg']}" for e in errs) if errs else "通过")[:MSG_CAP * 2]}


OPS = {"generate": generate, "check_project": check_project, "dsl_verify": dsl_verify}


def call(op, args):
    try:
        return OPS[op](**args)
    except Exception as e:  # noqa: BLE001
        return {"ok": "否", "msg": f"{type(e).__name__}: {e}"[:MSG_CAP]}


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
    req = json.loads(sys.stdin.read())
    print(json.dumps(call(req["op"], req["args"]), ensure_ascii=False))
