# -*- coding: utf-8 -*-
"""教师端桌面入口：app.pyw --教师 / --teacher / KG_TEACHER=1，和 teacher.pyw。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_teacher_entry.py

  一、window_target：带教师参数（中英文、环境变量）打开 /teacher、标题加「· 教师端」，
      不带仍是 /、标题不变；parse_teacher 把参数去掉，别的参数原样
  二、app.pyw 的 main 走一遍（窗口、建库、服务全换成假的，不开窗口、不碰 kg/app.db）：
      --teacher 时 create_window 拿到 /teacher，默认拿到 /；登录开关照旧
  三、teacher.pyw：插上 --teacher 后按 __main__ 跑 app.pyw
"""

import io
import os
import runpy
import sys
import types
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import kg.__main__ as kgmain                                        # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✓ {msg}")
    else:
        failed += 1
        print(f"  ✗ {msg}")


def load_app():
    path = str(ROOT / "kg" / "app.pyw")
    mod = module_from_spec(spec_from_loader("kg_app_pyw", SourceFileLoader("kg_app_pyw", path)))
    mod.__spec__.loader.exec_module(mod)
    return mod


def main():
    app = load_app()

    print("一、window_target")
    for argv, env in ((["--teacher"], {}), (["--教师"], {}), ([], {"KG_TEACHER": "1"}),
                      (["--mock", "--teacher", "--login"], {})):
        url, title = app.window_target(8180, "知识图谱（模拟）", argv, env)
        check(url.endswith("/teacher") and title == "知识图谱（模拟） · 教师端",
              f"{argv} {env} → {url}，标题 {title}")
    for argv, env in (([], {}), (["--mock"], {}), ([], {"KG_TEACHER": "0"}), ([], {"KG_TEACHER": ""})):
        url, title = app.window_target(8180, "知识图谱", argv, env)
        check(url == "http://127.0.0.1:8180/" and title == "知识图谱", f"{argv} {env} → {url}（学生端）")
    check(kgmain.parse_teacher(["--mock", "--教师", "--port", "1"], {}) == (True, ["--mock", "--port", "1"]),
          "parse_teacher 去掉 --教师，别的原样")
    check(kgmain.parse_teacher(["--teacher"], {})[0] and not kgmain.parse_teacher([], {})[0],
          "parse_teacher：--teacher 是，默认不是")

    print("二、app.pyw 的 main（全是假的）")
    import gen.project
    windows, made = [], []
    fake_webview = types.ModuleType("webview")
    fake_webview.create_window = lambda title, url, **kw: windows.append((title, url))
    fake_webview.start = lambda: None
    fake_app = types.SimpleNamespace(run=lambda **kw: None)
    old = (sys.modules.get("webview"), kgmain.setup, gen.project.make_app, os.environ.get("KG_TEACHER"))
    sys.modules["webview"] = fake_webview
    kgmain.setup = lambda quiet=False: 0
    gen.project.make_app = lambda root, real=False, **kw: made.append(kw) or (fake_app, None)
    app.start_log = lambda: None
    app.check = lambda: []
    app.free_port = lambda start=8180: 8999
    app.time = types.SimpleNamespace(sleep=lambda s: None, strftime=lambda *a: "")
    os.environ.pop("KG_TEACHER", None)
    try:
        for argv, want, login in ((["--mock", "--teacher"], "/teacher", False),
                                  (["--mock", "--教师", "--login"], "/teacher", True),
                                  (["--mock"], "/", False)):
            windows.clear()
            made.clear()
            with redirect_stdout(io.StringIO()):
                code = app.main(argv)
            title, url = windows[0]
            check(code == 0 and url == f"http://127.0.0.1:8999{want}"
                  and ("教师端" in title) == (want == "/teacher")
                  and (made[0].get("login") is True) == login,
                  f"main({argv}) → {url}，标题 {title}，login={made[0].get('login', False)}")
    finally:
        if old[0] is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = old[0]
        kgmain.setup, gen.project.make_app = old[1], old[2]
        if old[3] is not None:
            os.environ["KG_TEACHER"] = old[3]

    print("三、teacher.pyw")
    seen = {}
    old_run, old_argv = runpy.run_path, sys.argv
    runpy.run_path = lambda path, run_name=None: seen.update(path=path, run_name=run_name, argv=list(sys.argv))
    sys.argv = [str(ROOT / "kg" / "teacher.pyw"), "--mock"]
    try:
        old_run(str(ROOT / "kg" / "teacher.pyw"), run_name="__main__")
    finally:
        runpy.run_path, sys.argv = old_run, old_argv
    check(Path(seen.get("path", "")) == ROOT / "kg" / "app.pyw" and seen.get("run_name") == "__main__",
          f"teacher.pyw 按 __main__ 跑 {seen.get('path')}")
    check(seen.get("argv", [])[1:] == ["--teacher", "--mock"], f"teacher.pyw 带上 --teacher：{seen.get('argv', [])[1:]}")
    src = (ROOT / "kg" / "teacher.pyw").read_text(encoding="utf-8")
    check("def build_app" not in src and "webview" not in src, "teacher.pyw 不复制 app.pyw 的逻辑")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
