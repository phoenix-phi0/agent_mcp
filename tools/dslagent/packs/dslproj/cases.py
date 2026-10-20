"""dslproj 的用例运行器：按 contracts/<模块>.md 的「## 用例」跑，每个用例在空库上单独跑，时间固定，可单独跑一个模块。

    python -m tools.dslagent.packs.dslproj.cases --project DIR --module NAME [--now "2026-01-01 09:00:00"]

做法：项目拷到临时目录 → 每个用例各自新建 app.db（按 模块 + 上游模块 的 entities/*.entity 建表）→ 先（造数据：直接插行 / 调公开函数）
→ 调用（用 DSL 引擎跑 `调用 模块.函数 k=v 出错时 e`，业务层 services/ 整个目录加载）→ 核对 得 / 报错 / 库。
每次「调用」（先 的和正式的）后都 settle() 等「后台执行」触发的后台任务跑完，再往下走，不然「库」核对可能对上还没写完的数据。
环境变量 DSL_NOW 固定为 --now（缺省 2026-01-01 09:00:00），所以 `当前时间` 的结果确定。
输出 unittest 风格（"FAIL: 名: 原因" … "Ran N tests"），退出码 0 = 全过。
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from . import project as P

DEFAULT_NOW = "2026-01-01 09:00:00"
COPY_IGNORE = shutil.ignore_patterns(".*", "__pycache__", "node_modules", "venv", "env", "*.pyc", "*.db", "*.db-*", "sessions")


def build_sql(ws, modules):
    """modules 的 entities/<模块>.entity 拼起来 → 建表 SQL；缺实体文件的模块报 ValueError。"""
    from tools.entity import render_sql
    texts, missing = [], []
    for m in modules:
        f = Path(ws) / "entities" / f"{m}.entity"
        if f.is_file():
            texts.append(f.read_text(encoding="utf-8"))
        else:
            missing.append(m)
    if missing:
        raise ValueError("缺 " + "、".join(f"entities/{m}.entity" for m in missing))
    return render_sql("\n\n".join(texts), strict=True) if texts else ""


def settle(timeout=60):
    """等这次「调用」触发的后台任务（后台执行）跑完再往下核对返回值 / 库，不然可能对比到还没写完的库。
    超时抛 TimeoutError（用例应判超时失败，不要悄悄比对还没写完的库）。"""
    from tools.dsl import wait_background
    if not wait_background(timeout=timeout):
        raise TimeoutError(f"后台任务 {timeout} 秒内没跑完")


def _val(v):
    return "" if v == "空" else v


def _same(actual, expected):
    a, e = "" if actual is None else str(actual), _val(expected)
    if a == e:
        return True
    try:
        return float(a) == float(e)
    except ValueError:
        return a.lower() == e.lower() and a.lower() in ("true", "false")


def _table_cols(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]


def _where(con, table, kv):
    cols = _table_cols(con, table)
    if not cols:
        raise ValueError(f"库里没有表「{table}」")
    bad = [k for k in kv if k not in cols]
    if bad:
        raise ValueError(f"表「{table}」没有列 {bad}（有 {cols}）")
    return " AND ".join(f"{k} = ?" for k in kv), [_val(v) for v in kv.values()]


def run_case(ws, sql, module, u):
    """在空库上跑一个用例 → "" 或失败原因。"""
    from tools import packs
    from tools.dsl import DSLEngine
    from tools.dsl_http import DEFAULT_PACKS
    from tools.dsl_service import get_services
    from tools.mock import MockClient
    db = Path(ws) / "app.db"
    for suf in ("", "-wal", "-shm", "-journal"):
        try:
            Path(str(db) + suf).unlink()
        except OSError:
            pass
    con = sqlite3.connect(db)
    try:
        if sql:
            con.executescript(sql)
        con.commit()
        for st in u["先"]:
            if st["种类"] == "数据":
                cols = _table_cols(con, st["表"])
                bad = [k for k in st["值"] if k not in cols]
                if not cols or bad:
                    return "先 数据：" + (f"库里没有表 {st['表']}" if not cols else f"表 {st['表']} 没有列 {bad}")
                con.execute(f"INSERT INTO {st['表']}({', '.join(st['值'])}) VALUES({', '.join('?' * len(st['值']))})",
                            [_val(v) for v in st["值"].values()])
        con.commit()
    except sqlite3.Error as e:
        return f"造数据失败：{e}"
    finally:
        con.close()
    eng = DSLEngine(MockClient(offline=True), workdir=Path(ws), verbose=False,
                    verbs=packs.registry(DEFAULT_PACKS, Path(ws)), verbs_root=packs.verbs_root())
    svc = get_services(Path(ws) / "services")
    svc.refresh()
    if svc.errors:
        return "业务层加载失败：" + "；".join(svc.errors)[:600]
    eng.services = svc
    eng.svc_module = None

    def call(target, args, tag):
        tgt = target if "." in target else f"{module}.{target}"
        for i, v in enumerate(args.values()):
            eng.vars[f"x{tag}a{i}"] = _val(v)
        txt = " ".join(f"{k}={{x{tag}a{i}}}" for i, k in enumerate(args))
        eng.vars.pop(f"x{tag}r", None)
        eng.vars.pop(f"x{tag}e", None)
        eng.run(f"设 x{tag}r = 调用 {tgt}{(' ' + txt) if txt else ''} 出错时 x{tag}e")
        return eng.vars.get(f"x{tag}r"), eng.vars.get(f"x{tag}e")

    try:
        for i, st in enumerate(u["先"]):
            if st["种类"] == "调用":
                _, err = call(st["目标"], st["参数"], f"p{i}")
                settle()
                if err not in ("", None):
                    return f"前置 {st['目标']} 报错 {err}"
        r, err = call(u["调用"]["目标"], u["调用"]["参数"], "c")
        settle()
    except TimeoutError as e:
        return str(e)
    except Exception as e:  # noqa: BLE001  脚本报错就是用例失败
        return f"{type(e).__name__}: {str(e)[:500]}"
    if u["报错"] is not None:
        if err in ("", None):
            return f"应该报错 {u['报错']}，实际没报错（返回 {r!r}）"
        code = err.get("code") if isinstance(err, dict) else None
        if str(code) != str(u["报错"]):
            return f"应该报错 {u['报错']}，实际是 {err}"
    else:
        if err not in ("", None):
            return f"不该报错，实际报错 {err}"
        if u["为空"] and r not in ("", None, {}, []):
            return f"应该返回空，实际 {r!r}"
        if u["有返回"] and r in ("", None, {}, []):
            return "应该有返回值，实际为空"
        for k, v in (u["得"] or {}).items():
            got = r.get(k) if isinstance(r, dict) else None
            if not _same(got, v):
                return f"{k} 应为 {_val(v)!r}，实际 {got!r}（返回 {r!r}）"
    con = sqlite3.connect(db)
    try:
        for chk in u["库"]:
            if chk["种类"] == "共":
                n = con.execute(f"SELECT count(*) FROM {chk['表']}").fetchone()[0]
                if n != chk["行数"]:
                    return f"库 {chk['表']} 应有 {chk['行数']} 行，实际 {n} 行"
            else:
                w, vals = _where(con, chk["表"], chk["值"])
                n = con.execute(f"SELECT count(*) FROM {chk['表']} WHERE {w}", vals).fetchone()[0]
                if chk["种类"] == "含" and n == 0:
                    return f"库 {chk['表']} 里没有 {chk['值']} 这一行"
                if chk["种类"] == "无" and n > 0:
                    return f"库 {chk['表']} 里不该有 {chk['值']} 这一行"
    except (sqlite3.Error, ValueError) as e:
        return f"库核对失败：{e}"
    finally:
        con.close()
    return ""


def run(project, module, now=None):
    """→ {"全过": bool, "总数": n, "失败": [{"名","原因"}], "原因": 汇总文字}。不改 project；加载检查另见 project.load_problems。"""
    project = Path(project).resolve()
    old = os.environ.get("DSL_NOW")
    os.environ["DSL_NOW"] = now or old or DEFAULT_NOW
    tmp = Path(tempfile.mkdtemp(prefix="dslproj_cases_"))
    try:
        try:
            c, _ = P.load_contract(project, module)
        except P.ProjError as e:
            return _res(0, [], str(e))
        ws = tmp / "p"
        shutil.copytree(project, ws, ignore=COPY_IGNORE, symlinks=True)
        try:
            sql = build_sql(ws, P.closure(project, module))
        except Exception as e:  # noqa: BLE001
            return _res(len(c["用例"]), [{"名": "建表", "原因": f"{type(e).__name__}: {str(e)[:400]}"}], "")
        fails = []
        for u in c["用例"]:
            why = run_case(ws, sql, module, u)
            if why:
                fails.append({"名": u["名"], "原因": why})
        return _res(len(c["用例"]), fails, "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if old is None:
            os.environ.pop("DSL_NOW", None)
        else:
            os.environ["DSL_NOW"] = old


def _res(n, fails, why):
    parts = ([why] if why else []) + [f"用例 {f['名']}：{f['原因']}" for f in fails]
    return {"全过": not parts, "总数": n, "失败": fails, "原因": "\n".join(parts)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    r = run(a.project, a.module, a.now)
    for f in r["失败"]:
        print(f"FAIL: {f['名']}: {f['原因']}")
    if r["原因"] and not r["失败"]:
        print(f"ERROR: {r['原因']}")
    print(f"Ran {r['总数']} tests")
    print("OK" if r["全过"] else f"FAILED (failures={len(r['失败'])})")
    return 0 if r["全过"] else 1


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[4]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.exit(main())
