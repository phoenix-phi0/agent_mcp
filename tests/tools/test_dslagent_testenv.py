# -*- coding: utf-8 -*-
"""跑项目测试的子进程看不到 DSLAGENT_* 环境变量（DSLAGENT_TEST_CMD 等只给 DSL 引擎自己读）。

    cd /home/ysc/mcp && TMPDIR=/home/ysc/.cache/tmp .venv/bin/python tests/tools/test_dslagent_testenv.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.dslagent import runner as RN          # noqa: E402
from tools.dslagent import reason as R           # noqa: E402
from tools.dslagent.legacy import reason_rules as RR    # noqa: E402
from tools.dslagent.verify import code as VC     # noqa: E402

FAILS = []


def check(ok, msg):
    print(("OK   " if ok else "FAIL ") + msg)
    if not ok:
        FAILS.append(msg)


def dsl_vars(env):
    return sorted(k for k in env if k.startswith("DSLAGENT_"))


os.environ["DSLAGENT_TEST_CMD"] = "/nonexistent/cmd tests/acc"
os.environ["DSLAGENT_STATE"] = "/tmp/x"
os.environ["KEEP_ME"] = "1"
m = RN._verb_module("跑测试")

# 一、公共函数与 test_env
e = m.clean_env(FOO="1")
check(dsl_vars(e) == [] and e["FOO"] == "1" and e["KEEP_ME"] == "1", "clean_env 去掉 DSLAGENT_*、保留其余、可加额外项")
check(dsl_vars(m.clean_env({"DSLAGENT_A": "1", "B": "2"})) == [] and m.clean_env({"DSLAGENT_A": "1", "B": "2"}) == {"B": "2"},
      "clean_env 可传 base")
e = m.test_env()
check(dsl_vars(e) == [] and e["PYTHONDONTWRITEBYTECODE"] == "1", "test_env 无 DSLAGENT_*，仍不写 pyc")
check(dsl_vars(RR._pycache_env()) == [], "reason._pycache_env 无 DSLAGENT_*")

# 二、各入口起的子进程真看不到
with tempfile.TemporaryDirectory() as d:
    proj = Path(d)
    (proj / "dump.py").write_text(
        "import os,sys\nbad=sorted(k for k in os.environ if k.startswith('DSLAGENT_'))\n"
        "print('BAD' if bad else 'CLEAN', bad)\nsys.exit(1 if bad else 0)\n", encoding="utf-8")
    rc, out = m.run_raw(proj, f"{sys.executable} dump.py", 30)
    check(rc == 0 and "CLEAN" in out, f"run_raw 的测试子进程无 DSLAGENT_*：{out.strip()}")
    r = VC.full_test(proj, f"{sys.executable} dump.py")
    check(r["passed"] is True, f"verify.full_test 走 run_raw：{r}")
    bdir = proj / "b"
    bdir.mkdir()
    (bdir / "test_boundary_v2.py").write_text(
        "import os, unittest\nclass T(unittest.TestCase):\n    def test_env(self):\n"
        "        self.assertEqual([k for k in os.environ if k.startswith('DSLAGENT_')], [])\n", encoding="utf-8")
    b = VC.run_boundary(str(proj), f"{sys.executable} -m pytest", bdir)
    check(b.get("ok") and not b.get("failed") and not b.get("broken"), f"run_boundary 子进程无 DSLAGENT_*：{ {k: b.get(k) for k in ('ok','failed','broken')} }")

    # 三、引擎自己仍按 DSLAGENT_TEST_CMD 选命令（命令不存在 → 起不来，而不是跑默认命令）
    rc, out = m.run_raw(proj)
    check(rc is None and "起不来" in out, f"run_raw 不传命令时仍读 DSLAGENT_TEST_CMD：{out.strip()[:60]}")

print("全过" if not FAILS else f"失败 {len(FAILS)} 条")
sys.exit(1 if FAILS else 0)
