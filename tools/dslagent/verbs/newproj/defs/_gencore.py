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


def role_files(roles):
    """清单里的角色 → 接 gen private 登录注册的两个补丁文件 queries/user_auth.sql、routes/auth_roles.zs
    （文本在 gen/templates/private/project/，私有套的参数「角色」），以及注册默认角色（最后一个）。"""
    from gen.project import render_auth
    names = [str(r).strip() for r in roles if str(r).strip()]
    allf = render_auth(roles=names)
    return {k: allf[k] for k in ("queries/user_auth.sql", "routes/auth_roles.zs") if k in allf}, names[-1] if names else ""


def apply_roles(root, roles):
    """在 add_auth 之后、ensure_db 之前调：给 entities/user.entity 加 role 列，写 user_auth.sql 与 auth_roles.zs（已存在的不覆盖）。
    新项目直接用 add_auth(roles=…) 一步到位；这里是对已有项目补上。"""
    from gen.project import render_auth
    root = Path(root)
    files, default = role_files(roles)
    log = []
    ue = root / "entities" / "user.entity"
    if ue.is_file():
        t = ue.read_text(encoding="utf-8")
        if not re.search(r"^\s*字段\s+role\s", t, re.M):
            line = next(x for x in render_auth(roles=roles)["entities/user.entity"].splitlines(True) if re.match(r"^\s*字段\s+role\s", x))
            t = t.replace("\n结束", "\n" + line + "结束", 1) if "\n结束" in t else t + line
            ue.write_text(t, encoding="utf-8")
            log.append(f"  user 实体加 role 列（默认 {default}）")
    for rel, text in files.items():
        p = root / rel
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        log.append(f"  写入 {rel}")
    return log


def generate(root, tpl="full", only=None, force=False, roles=None, no_register=False):
    from gen import project as P
    PE, _ = _gen_errors()
    root = Path(root)
    log = []
    try:
        log += P.init(root, sample=False)
        if tpl == "private":
            log += P.add_auth(root, roles=roles, no_register=no_register)
            if roles:
                log += apply_roles(root, roles)    # 已有项目补角色；新项目上一步已写全，这里无事可做
            ents = P.load_entities(root)
            log += P.generate(root, "private", only=only or None, force=force)
            rest = [e.name for e in ents if "owner" not in [f.name for f in e.fields] and (not only or e.name in only)]
            if rest:
                log += P.generate(root, "full", only=rest, force=force)
            # 权限由程序套：角色 ≥2 时 gen 的增删改查只许第一个（教师类）角色、user 查询不出 password_hash、按需关公开注册
            log += P.apply_perms(root, roles, no_register)
        else:
            log += P.generate(root, tpl, only=only or None, force=force)
        log.append(P.ensure_db(root))
    except PE as e:
        return {"ok": "否", "msg": str(e)[:MSG_CAP]}
    except Exception as e:  # noqa: BLE001  模板缺失等也要变成 msg
        return {"ok": "否", "msg": f"{type(e).__name__}: {e}"[:MSG_CAP]}
    return {"ok": "是", "msg": "\n".join(x.rstrip() for x in log)[:MSG_CAP]}


def apply_perms(root, roles=None, no_register=False):
    """对已有项目重新套 gen 权限（resume 用）。只改 gen 生成的增删改查接口头行 / user 查询 / 注册块，模型追加的内容不动；可重复调用。"""
    from gen import project as P
    PE, _ = _gen_errors()
    try:
        log = P.apply_perms(Path(root), roles or [], no_register)
    except PE as e:
        return {"ok": "否", "msg": str(e)[:MSG_CAP]}
    return {"ok": "是", "msg": "\n".join(x.rstrip() for x in log)[:MSG_CAP]}


def dup_routes(root):
    seen = {}
    for f in sorted((Path(root) / "routes").rglob("*.zs")):
        for m in re.finditer(r"^接口\s+(\w+)\s+(\S+)", f.read_text(encoding="utf-8"), re.M):
            seen.setdefault(m.groups(), []).append(str(f.relative_to(root)))
    return [f"接口 {k[0]} {k[1]} 重复出现在 {'、'.join(v)}" for k, v in seen.items() if len(v) > 1]


UI_FAIL = re.compile(r"^\s*\[提示\]\s*(\S+?)：解析失败\s*(.*)$")


def ui_parse_failures(lines):
    """gen build 对解析失败的 .ui 只在返回的提示行里写「<文件>：解析失败 <原话>」并跳过（ui_site.merge 为了让编辑器容忍写到一半的文件），
    不抛错；检查项目把它当失败：返回「界面 <文件> 解析失败（gen 原话）：…」列表。"""
    out = []
    for ln in lines or []:
        m = UI_FAIL.match(str(ln))
        if m:
            out.append(f"界面 ui/{m.group(1)} 编译不过，gen 原话：{m.group(2).strip()}")
    return out


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
            lines = P.build(root)
            errs += ui_parse_failures(lines)
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


OPS = {"generate": generate, "apply_perms": apply_perms, "check_project": check_project, "dsl_verify": dsl_verify}


def call(op, args):
    try:
        return OPS[op](**args)
    except Exception as e:  # noqa: BLE001
        return {"ok": "否", "msg": f"{type(e).__name__}: {e}"[:MSG_CAP]}


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
    req = json.loads(sys.stdin.read())
    print(json.dumps(call(req["op"], req["args"]), ensure_ascii=False))
