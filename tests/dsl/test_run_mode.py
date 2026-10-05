# -*- coding: utf-8 -*-
"""运行模式：脚本里的 {run_mode}（real / mock），以及 py -m kg 的默认真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_run_mode.py

  一、Router：real=True → real，real=False → mock；请求体伪造「run_mode」盖不掉；
      注入的是英文名，旧的中文名 {当前模式} 不再注入（原样留着）
  三、kg/app.pyw 的 build_app：默认 make_app(real=True)，--mock / KG_MOCK 才是 False；
      窗口标题带模式；脚本抛错时接口回 500 + messages（前端能显示）
  二、py -m kg：默认给 gen run 加 --real；--mock / KG_MOCK=1 不加；
      启动打印一行模式，模拟时说明回复不是真模型，真模型时列出档位，不含 key
"""

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl_http import Router         # noqa: E402
import kg.__main__ as kgmain              # noqa: E402
import gen.project                        # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def mode_of(real, forged=None):
    tmp = Path(tempfile.mkdtemp(prefix="run_mode_"))
    (tmp / "routes").mkdir()
    (tmp / "routes" / "m.zs").write_text(
        "接口 POST /m 动作 m\n  返回 {\"mode\":\"{run_mode}\",\"req\":\"{request.run_mode}\","
        "\"old\":\"{当前模式}\"}\n结束\n",
        encoding="utf-8")
    r = Router(tmp / "routes", tmp, tmp / "sessions", real=real)
    ep = next(iter(r.table.values()))
    body, status = r.handle(ep, {"run_mode": forged} if forged else {})
    return status, body


def run_kg(argv, env=None):
    seen = {}
    old_main, old_env, old_setup = gen.project.main, dict(os.environ), kgmain.setup
    gen.project.main = lambda a: seen.setdefault("argv", a) and 0
    kgmain.setup = lambda *a, **k: 0
    os.environ.pop("KG_MOCK", None)
    os.environ.update(env or {})
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            kgmain.main(argv)
    finally:
        gen.project.main, kgmain.setup = old_main, old_setup
        os.environ.clear()
        os.environ.update(old_env)
    return seen.get("argv"), buf.getvalue()


def app_build(argv, env):
    """加载 app.pyw，截住它传给 make_app 的参数。返回 (real, title)。"""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    path = str(ROOT / "kg" / "app.pyw")
    mod = module_from_spec(spec_from_loader("kg_app_pyw", SourceFileLoader("kg_app_pyw", path)))
    mod.__spec__.loader.exec_module(mod)
    seen = {}
    old = gen.project.make_app
    gen.project.make_app = lambda root, real=False: seen.update(real=real) or (None, None)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            _, mock, title = mod.build_app(argv, env)
    finally:
        gen.project.make_app = old
    return seen["real"], mock, title, buf.getvalue()


def main():
    print("一、脚本里的 run_mode")
    for real, want in ((True, "real"), (False, "mock")):
        st, body = mode_of(real)
        check(st == 200 and body.get("mode") == want and body.get("req") == want,
              f"real={real} → {body}")
    check(body.get("old") == "{当前模式}", f"旧的中文名不再注入，原样留着：{body}")
    st, body = mode_of(False, forged="real")
    check(body.get("mode") == "mock" and body.get("req") == "mock", f"请求体伪造 real 盖不掉：{body}")

    print("二、py -m kg 的默认")
    argv, out = run_kg([])
    check(argv and argv[0] == "run" and "--real" in argv, f"默认带 --real：{argv}")
    check(out.lstrip().startswith("模式：真模型") and "快=" in out and "key" not in out.lower(),
          f"打印真模型和档位：{out.strip()[:120]}")
    argv, out = run_kg(["--port", "8200"])
    check("--real" in argv and "--port" in argv and "8200" in argv, f"其余参数照传：{argv}")
    argv, out = run_kg(["--mock"])
    check("--real" not in argv and "--mock" not in argv, f"--mock 不带 --real、也不把 --mock 交给 gen：{argv}")
    check("模拟" in out and "不是真模型" in out, f"打印模拟：{out.strip()}")
    argv, out = run_kg(["run"], env={"KG_MOCK": "1"})
    check("--real" not in argv and "模拟" in out, f"KG_MOCK=1 等于 --mock：{argv}")
    argv, out = run_kg([], env={"KG_MOCK": "0"})
    check("--real" in argv, "KG_MOCK=0 还是真模型")

    print("三、kg/app.pyw")
    real, mock, title, out = app_build([], {})
    check(real is True and mock is False, f"默认 real=True：{real}")
    check(title.startswith("知识图谱（真模型：") and "key" not in title.lower(), f"标题：{title}")
    check(out.startswith("模式：真模型"), "启动打印模式行")
    real, mock, title, out = app_build(["--mock"], {})
    check(real is False and title == "知识图谱（模拟）", f"--mock → real=False，标题：{title}")
    real, mock, title, out = app_build([], {"KG_MOCK": "1"})
    check(real is False and title == "知识图谱（模拟）", "KG_MOCK=1 → real=False")
    real, _, _, _ = app_build([], {"KG_MOCK": "0"})
    check(real is True, "KG_MOCK=0 → real=True")

    print("四、脚本出错：500 + messages")
    tmp = Path(tempfile.mkdtemp(prefix="run_err_"))
    (tmp / "routes").mkdir()
    (tmp / "routes" / "e.zs").write_text(
        "接口 POST /e 动作 e\n  用包 db\n  设 行表 = 查询 app.db no_such_query\n  返回 {\"ok\":1}\n结束\n",
        encoding="utf-8")
    c = Router(tmp / "routes", tmp, tmp / "sessions").app().test_client()
    r = c.post("/e", json={})
    d = r.get_json() or {}
    msgs = d.get("messages") or []
    check(r.status_code == 500 and msgs and msgs[0].get("kind") == "no" and msgs[0].get("text"),
          f"{r.status_code} {str(d)[:120]}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
