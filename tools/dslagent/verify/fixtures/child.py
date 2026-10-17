"""子进程：在临时工作区里按名字调用一个目标（动词走注册表；模块函数 import 后调）。由 verify/bound_table.py 起。
stdin: JSON {root, kind, pack_dir, name, module, func, inputs:[{参数名: 值}], fixture, twice, ws_files}
stdout: 每个输入一行 JSON {i, exc, rtype, rep, same}；末行 {"done":1}。值里 "$WS…"/"$OUT" 会替换成真实路径，{"$Path": s} 转 Path。
本进程的当前目录 = 临时工作区；HOME / CBATCH_HOME / GBATCH_HOME 等都指向临时目录；单次调用 5 秒用 setitimer 打断；结果上限 200000 字符。"""
import contextlib
import io
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import builders as fixtures  # noqa: E402

CALL_TIMEOUT = 5.0


class CallTimeout(BaseException):
    pass


def _alarm(sig, frm):
    raise CallTimeout("单次调用超过 5s")


def main():
    req = json.loads(sys.stdin.read())
    tmp = Path(tempfile.mkdtemp(prefix="bp_", dir=os.environ.get("BP_TMP") or None)).resolve()
    ws = fixtures.build_workspace(tmp)
    for rel, txt in (req.get("ws_files") or {}).items():
        p = ws / rel
        if p.resolve() != ws and ws.resolve() not in p.resolve().parents:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(tmp)
    os.environ["CBATCH_HOME"] = str(tmp / "cb_jobs")
    os.environ["GBATCH_HOME"] = str(tmp / "gb_jobs")
    os.environ["TMPDIR"] = str(tmp)
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        os.environ[k] = str(tmp / k.lower())
    if req.get("fixture") in fixtures.BUILDERS:
        fixtures.BUILDERS[req["fixture"]](tmp)
    os.chdir(ws)
    root = Path(req["root"]).resolve()
    sys.path.insert(0, str(root))
    out = tmp / "outside.txt"

    def dec(v):
        if isinstance(v, str):
            return v.replace("$WS", str(ws)).replace("$OUT", str(out))
        if isinstance(v, dict) and "$Path" in v:
            return Path(dec(v["$Path"]))
        return v

    def norm(s):
        return s.replace(str(ws), "$WS").replace(str(tmp), "$TMP").replace(str(root), "$ROOT")

    # ---- 取可调用对象
    try:
        if req["kind"] == "verb":
            from tools.verbs import VerbRegistry
            reg = VerbRegistry()
            reg.load_pack(root / req["pack_dir"], ws)
            if not reg.has(req["name"]):
                print(json.dumps({"fatal": f"注册表里没有动词 {req['name']}；警告：{reg.warnings[:3]}"}, ensure_ascii=False))
                return
            _, impl = reg.resolve(req["name"])
            params = reg.params_of(req["name"])

            def call(kw):
                bound = {k: v for k, v in kw.items()}
                bad = [k for k in bound if k not in params]
                if bad:
                    raise TypeError(f"动词 {req['name']} 没有参数 {bad}")
                return impl(**bound)
        else:
            import importlib
            mod = importlib.import_module(req["module"])
            fn = getattr(mod, req["func"])
            call = lambda kw: fn(**kw)  # noqa: E731
    except BaseException as e:  # noqa: BLE001
        print(json.dumps({"fatal": f"加载失败 {type(e).__name__}: {str(e)[:300]}"}, ensure_ascii=False))
        return

    signal.signal(signal.SIGALRM, _alarm)

    def run_once(kw):
        signal.setitimer(signal.ITIMER_REAL, CALL_TIMEOUT)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                r = call(kw)
                if hasattr(r, "__next__") or type(r).__name__ == "generator":
                    r = list(r)
            return ("ok", r)
        except CallTimeout as e:
            return ("exc", e)
        except BaseException as e:  # noqa: BLE001
            return ("exc", e)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    def show(res):
        k, v = res
        if k == "exc":
            return {"exc": f"{type(v).__name__}: {norm(str(v))[:200]}", "rtype": None, "rep": None}
        try:
            rep = json.dumps(v, ensure_ascii=False, sort_keys=True, default=lambda o: str(o) if isinstance(o, os.PathLike) else (o.decode("utf-8", "replace") if isinstance(o, bytes) else f"<{type(o).__name__}>{o}"))
        except Exception:
            rep = repr(v)
        return {"exc": None, "rtype": type(v).__name__, "rep": norm(rep)[:200000]}

    for i, kw0 in enumerate(req["inputs"]):
        kw = {k: dec(v) for k, v in kw0.items()}
        t0 = time.time()
        a = show(run_once(kw))
        b = show(run_once({k: dec(v) for k, v in kw0.items()})) if req.get("twice", True) else a
        a["same"] = (a["exc"], a["rtype"], a["rep"]) == (b["exc"], b["rtype"], b["rep"])
        a["i"], a["sec"] = i, round(time.time() - t0, 3)
        print(json.dumps(a, ensure_ascii=False), flush=True)
    print(json.dumps({"done": 1}), flush=True)


if __name__ == "__main__":
    main()
