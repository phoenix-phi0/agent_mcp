# -*- coding: utf-8 -*-
"""当前模式：脚本里的 {当前模式}（real / mock），以及 py -m kg 的默认真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_run_mode.py

  一、Router：real=True → real，real=False → mock；请求体伪造「当前模式」盖不掉
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
        "接口 POST /m 动作 m\n  返回 {\"mode\":\"{当前模式}\",\"req\":\"{请求.当前模式}\"}\n结束\n",
        encoding="utf-8")
    r = Router(tmp / "routes", tmp, tmp / "sessions", real=real)
    ep = next(iter(r.table.values()))
    body, status = r.handle(ep, {"当前模式": forged} if forged else {})
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


def main():
    print("一、脚本里的当前模式")
    for real, want in ((True, "real"), (False, "mock")):
        st, body = mode_of(real)
        check(st == 200 and body.get("mode") == want, f"real={real} → {body}")
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

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
