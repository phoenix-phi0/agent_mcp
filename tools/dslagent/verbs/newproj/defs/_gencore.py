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


OPS = {"generate": generate, "check_project": check_project}


def call(op, args):
    try:
        return OPS[op](**args)
    except Exception as e:  # noqa: BLE001
        return {"ok": "否", "msg": f"{type(e).__name__}: {e}"[:MSG_CAP]}


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
    req = json.loads(sys.stdin.read())
    print(json.dumps(call(req["op"], req["args"]), ensure_ascii=False))
